"""Camera checks: a region reaching the frame's edge crops cleanly, darkness alerts Kafka at a steady pace, not once a frame, and the GPU and CPU decoders open a clip.
Run in the producer-consumer image: python3 src/util/test_camera.py"""
import json
import os
import subprocess
import sys
import tempfile
from unittest import mock

import numpy as np

SRC = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, SRC)
# The module reads the camera configuration when imported, and images hold none
os.chdir(tempfile.mkdtemp())
os.makedirs("src/Camera-Configuration")
with open("src/Camera-Configuration/camera_configuration.json", "w") as f:
    json.dump({"maingate": {"api-endpoint": "", "cctv-cameras": {"entry": {"cctv-camera-1": {}}, "exit": None}}}, f)
import multicam_stream_producer as producer  # noqa: E402
from util.generic_utilities import crop_and_mask_roi  # noqa: E402


def camera(frames, messages):
    """An IPCamera with no stream or Kafka: it reads the given frames and records what it would send."""
    cam = producer.IPCamera.__new__(producer.IPCamera)
    cam.__dict__.update(cam_name="maingate_entry_cctv-camera-1", cam_ip="10.0.0.1", roi=None, process_this_frame=True, frame_counter=0, too_dark=False, light_intensity_detection_buffer=[], darkness_buffer=[], adequate_lighting_message_sent=False, inadequate_lighting_message_logged=False, last_lighting_alert=0.0, shared_buffer=mock.Mock())

    def read():
        cam.frame, cam.grabbed = next(frames), True

    cam._read_one_frame = read
    cam.send_kafka_message = lambda message: messages.append(message)
    return cam


def test():
    frame = np.full((360, 640, 3), 200, np.uint8)
    roi = crop_and_mask_roi(frame, [[0, 0], [640, 0], [640, 360], [0, 360]])
    assert roi.shape == frame.shape, roi.shape
    assert crop_and_mask_roi(frame, [[10, 10], [100, 10], [100, 50], [10, 50]]).shape == (41, 91, 3)

    dark = np.zeros((360, 640, 3), np.uint8)
    light = np.full((360, 640, 3), 200, np.uint8)
    frames = iter([dark] * 500 + [light] * 200)
    messages = []
    cam = camera(frames, messages)
    now = [1000.0]
    with mock.patch.object(producer.time, "time", lambda: now[0]):
        for _ in range(500):
            cam.process_this_frame = True
            cam.place_frame_in_buffer()
            now[0] += 0.1  # 500 dark frames over 50 seconds
        alerts = [m for m in messages if m.startswith("ERROR")]
        assert len(alerts) == 2, len(alerts)  # the first once the buffer shows darkness, the next 30 seconds later
        for _ in range(200):
            cam.process_this_frame = True
            cam.place_frame_in_buffer()
            now[0] += 0.1
    assert sum(m.startswith("SUCCESS") for m in messages) == 1, messages[-3:]
    print(f"camera ok (region at the frame edge crops, {len(alerts)} alerts for 500 dark frames, recovery announced once)")


def test_decoders():
    """VIDEO_DECODE: auto opens a clip on the GPU when there is one (scaled to 640x360) and on the CPU otherwise (full
    size), gpu alone fails without one, and FFmpeg's errors never carry the camera's password."""
    from util import video_source
    assert video_source.masked("rtsp://admin:p%40ss@10.0.0.5:554/x failed") == "rtsp://***@10.0.0.5:554/x failed"
    clip = os.path.abspath("clip.mp4")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=10", "-t", "2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", clip], check=True)
    video_source.VIDEO_DECODE = "auto"
    stream = video_source.open_stream(clip)
    on_gpu = isinstance(stream, video_source._Primed)
    frames = [stream.read() for _ in range(3)]
    stream.release()
    assert all(ok for ok, _ in frames), "no frames"
    assert frames[0][1].shape == ((360, 640, 3) if on_gpu else (720, 1280, 3)), frames[0][1].shape
    if not on_gpu:
        video_source.VIDEO_DECODE = "gpu"
        assert video_source.open_stream(clip).read() == (False, None)
    print(f"decoders ok (auto decoded on the {'GPU' if on_gpu else 'CPU'}, passwords masked)")


if __name__ == "__main__":
    test()
    test_decoders()
