"""
Opens a camera stream for the producer. VIDEO_DECODE picks the decoder:
  cpu   OpenCV's FFmpeg on the CPU (the original path)
  gpu   FFmpeg on the GPU's video decoder (NVDEC), which also scales frames down, so the CPU only copies small ones
  auto  gpu, falling back to cpu for a connection the GPU cannot open (no GPU, no NVDEC library, an unsupported codec)
Both return an object with cv2.VideoCapture's read() and release().
"""
import json
import re
import socket
import subprocess
import threading
from urllib.parse import urlsplit
from collections import deque

import cv2
import numpy as np

from custom_logging import multicam_server_logger as logger
from parameters import FRAME_HEIGHT, FRAME_WIDTH, VIDEO_DECODE

# The NVDEC decoders FFmpeg calls <codec>_cuvid
CUVID_CODECS = {"h264", "hevc", "av1", "vp8", "vp9", "mjpeg", "mpeg1video", "mpeg2video", "mpeg4", "vc1"}
TIMEOUT_US = "5000000"  # a stalled stream ends read() after 5 s, so the producer reconnects as it does with OpenCV
# The CPU path's limits: an unreachable camera took OpenCV's default 21 s to fail and nothing bounded it; now opening gives
# up after 10 s and a stalled read after 5 s, so a reconnect cycle has a known worst case (D-051)
CPU_OPEN_TIMEOUT_MS = 10000
CPU_READ_TIMEOUT_MS = 5000
REACH_TIMEOUT_S = 5
DEFAULT_PORTS = {"rtsp": 554, "rtsps": 322, "http": 80, "https": 443}


def reachable(url: str) -> bool:
    """Whether the camera answers on its port at all. OpenCV's FFmpeg backend opens one stream at a time behind a global
    lock, so with many unreachable cameras each waited for all the others (18 of them made every reconnect take about
    3.5 minutes). A plain connection check runs in parallel and fails in seconds. A file or another scheme: True."""
    parts = urlsplit(url)
    try:
        port = parts.port or DEFAULT_PORTS.get(parts.scheme)
    except ValueError:
        return True
    if not parts.hostname or not port:
        return True
    try:
        socket.create_connection((parts.hostname, port), REACH_TIMEOUT_S).close()
        return True
    except OSError:
        return False


def masked(text: str) -> str:
    """Drops the login from any URL in text: FFmpeg's errors quote the camera URL, password included."""
    return re.sub(r"://[^@/\s]*@", "://***@", text)


def _input_options(url: str) -> list:
    if url.startswith("rtsp"):
        # TCP, as OpenCV uses: FFmpeg's default UDP failed from Docker Desktop with "Error during demuxing: Operation
        # not permitted", so every real camera fell back to the CPU
        return ["-rtsp_transport", "tcp", "-timeout", TIMEOUT_US]
    return ["-rw_timeout", TIMEOUT_US]


class NvdecCapture:
    """FFmpeg decodes on NVDEC with the codec's cuvid decoder, which also scales to FRAME_WIDTH x FRAME_HEIGHT unless
    full frames are needed (a region of interest is cropped from them). Frames arrive over a pipe as NV12, which OpenCV
    converts to BGR. Each camera is one FFmpeg process with its own CUDA context: about 131 MB of VRAM per camera on the
    laptop's RTX 4050 (decoder scaling; scale_cuda took 203 MB), so a camera the GPU has no room for fails to open."""

    def __init__(self, url: str, full_frame: bool):
        self.process = None
        self.errors = deque(maxlen=5)
        probe = subprocess.run(["ffprobe", "-v", "error", *_input_options(url), "-select_streams", "v:0",
                                "-show_entries", "stream=codec_name,width,height", "-of", "json", url],
                               capture_output=True, text=True, timeout=30)
        stream = (json.loads(probe.stdout or "{}").get("streams") or [{}])[0]
        codec, width, height = stream.get("codec_name"), stream.get("width"), stream.get("height")
        if not width or not height:
            raise RuntimeError(f"ffprobe found no video stream: {masked(probe.stderr.strip())[-300:]}")
        if codec not in CUVID_CODECS:
            raise RuntimeError(f"NVDEC has no decoder for {codec}")
        decoder = ["-c:v", f"{codec}_cuvid"]
        # The same rule as the CPU path: only frames larger than the target are scaled, and to exactly the target
        if not full_frame and (width > FRAME_WIDTH or height > FRAME_HEIGHT):
            width, height = FRAME_WIDTH, FRAME_HEIGHT
            decoder += ["-resize", f"{width}x{height}"]
        self.shape = (height * 3 // 2, width)  # NV12: a full-size luma plane, then a half-height interleaved chroma plane
        self.size = self.shape[0] * self.shape[1]
        self.process = subprocess.Popen(
            ["ffmpeg", "-nostdin", "-loglevel", "error", *_input_options(url), *decoder, "-i", url, "-an",
             "-f", "rawvideo", "-pix_fmt", "nv12", "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=self.size * 2)
        threading.Thread(target=self._keep_errors, daemon=True).start()

    def _keep_errors(self):
        # Some streams make FFmpeg repeat a warning every frame, so only the last lines are kept, logged once the stream ends
        for line in self.process.stderr:
            self.errors.append(masked(line.decode(errors="replace").strip()))

    def read(self):
        data = self.process.stdout.read(self.size)
        if len(data) < self.size:
            if self.errors:
                logger.warning("ffmpeg: " + " | ".join(self.errors))
                self.errors.clear()
            return False, None
        return True, cv2.cvtColor(np.frombuffer(data, np.uint8).reshape(self.shape), cv2.COLOR_YUV2BGR_NV12)

    def release(self):
        if self.process and self.process.poll() is None:
            self.process.kill()
            self.process.wait()


def open_stream(url: str, full_frame: bool = False):
    """Opens url with the decoder VIDEO_DECODE asks for. The caller reads the first frame to check the stream opened,
    so in auto mode a GPU attempt that yields no frame is closed and the camera is opened on the CPU instead. A camera that
    does not answer on its port is not handed to any decoder."""
    if not reachable(url):
        logger.error(f"{masked(url)} does not answer on its port; not trying to decode it")
        return _Primed(None, (False, None))
    if VIDEO_DECODE in ("gpu", "auto"):
        try:
            capture = NvdecCapture(url, full_frame)
            first = capture.read()
            if first[0]:
                return _Primed(capture, first)
            capture.release()
            reason = "no frame"
        except Exception as error:
            reason = masked(str(error))
        if VIDEO_DECODE == "gpu":
            logger.error(f"GPU decoding could not open {masked(url)}: {reason}")
            return _Primed(None, (False, None))
        logger.warning(f"GPU decoding could not open {masked(url)} ({reason}); using the CPU for this connection")
    return cv2.VideoCapture(url, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, CPU_OPEN_TIMEOUT_MS,
                                                  cv2.CAP_PROP_READ_TIMEOUT_MSEC, CPU_READ_TIMEOUT_MS])


class _Primed:
    """Hands back the frame open_stream already read, so the caller's first read() behaves as with OpenCV."""

    def __init__(self, capture, first):
        self.capture, self.first = capture, first

    def read(self):
        if self.first is not None:
            first, self.first = self.first, None
            return first
        return self.capture.read() if self.capture else (False, None)

    def release(self):
        if self.capture:
            self.capture.release()
