"""Camera checks: a region reaching the frame's edge crops cleanly and one that does not fit is reported, not crashed on,
darkness is judged on the region's own pixels and alerts Kafka at a steady pace, not once a frame, the GPU and CPU decoders open a clip, and the InsightFace client recovers from a connection error.
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
from util.generic_utilities import crop_and_mask_roi, resize_roi_to_area  # noqa: E402


def camera(frames, messages, roi=None):
    """An IPCamera with no stream or Kafka: it reads the given frames and records what it would send."""
    cam = producer.IPCamera.__new__(producer.IPCamera)
    cam.__dict__.update(cam_name="maingate_entry_cctv-camera-1", cam_ip="10.0.0.1", roi=roi, process_this_frame=True, frame_counter=0, shared_buffer=mock.Mock())
    cam.reset_lighting()

    def read():
        cam.frame, cam.grabbed = next(frames), True

    cam._read_one_frame = read
    cam.send_kafka_message = lambda message: messages.append(message)
    return cam


def run(cam, count, now, step=0.1):
    for _ in range(count):
        cam.place_frame_in_buffer()
        now[0] += step


def raises(call, text):
    try:
        call()
    except ValueError as error:
        assert text in str(error), error
    else:
        raise AssertionError(f"expected ValueError {text!r}")


def test():
    frame = np.full((360, 640, 3), 200, np.uint8)
    roi = crop_and_mask_roi(frame, [[0, 0], [640, 0], [640, 360], [0, 360]])
    assert roi.shape == frame.shape, roi.shape
    assert crop_and_mask_roi(frame, [[10, 10], [100, 10], [100, 50], [10, 50]]).shape == (41, 91, 3)
    raises(lambda: crop_and_mask_roi(frame, [[10, 10], [700, 10], [700, 50]]), "does not fit the 640x360")
    raises(lambda: crop_and_mask_roi(frame, [[-1, 10], [100, 10], [100, 50]]), "does not fit")
    raises(lambda: crop_and_mask_roi(frame, [[10, 10], [100, 10]]), "3 or more")
    raises(lambda: crop_and_mask_roi(frame, [[10, 10], [50, 10], [100, 10]]), "no area")
    raises(lambda: crop_and_mask_roi(frame, [[640, 0], [640, 100], [640, 360]]), "no area")
    raises(lambda: resize_roi_to_area(frame[:0]), "empty")

    # Darkness of a region is the mean of its own pixels: the black outside it does not count, black inside it does
    producer.CROP_ROI = True
    cam = camera(iter([]), [], roi=[[0, 0], [600, 0], [0, 300]])
    assert not cam.prepare(np.full((360, 640, 3), 120, np.uint8))[1], "the black outside a triangle made it dark"
    scene = np.full((360, 640, 3), 200, np.uint8)
    scene[:, 300:] = 0
    cam.roi = [[200, 0], [400, 0], [400, 360], [200, 360]]
    assert not cam.prepare(scene)[1]  # half 200, half 0: mean 100
    cam.roi = [[300, 0], [640, 0], [640, 360], [300, 360]]
    assert cam.prepare(scene)[1], "a dark door beside a bright lobby must count as dark"
    cam.roi = [[0, 0], [639, 0], [639, 1], [0, 1]]  # two rows of pixels
    assert cam.prepare(np.full((360, 640, 3), 40, np.uint8))[1] and not cam.prepare(np.full((360, 640, 3), 90, np.uint8))[1]
    cam.roi = None
    assert cam.prepare(np.full((1080, 1920, 3), 79, np.uint8))[1] and not cam.prepare(np.full((1080, 1920, 3), 80, np.uint8))[1]

    dark = np.zeros((360, 640, 3), np.uint8)
    light = np.full((360, 640, 3), 200, np.uint8)
    now = [1000.0]
    with mock.patch.object(producer.time, "monotonic", lambda: now[0]):
        # Until the window fills, dark frames are held back and nothing is announced
        messages = []
        cam = camera(iter([dark] * 50 + [light] * 49), messages)
        run(cam, 99, now)
        assert cam.shared_buffer.put.call_count == 49 and not messages, (cam.shared_buffer.put.call_count, messages)

        messages = []
        cam = camera(iter([dark] * 500 + [light] * 200), messages)
        run(cam, 500, now)  # 500 dark frames over 50 seconds
        alerts = [m for m in messages if m.startswith("ERROR")]
        assert len(alerts) == 2, len(alerts)  # the first once the window shows darkness, the next 30 seconds later
        run(cam, 200, now)
        assert sum(m.startswith("SUCCESS") for m in messages) == 1, messages[-3:]
        assert cam.shared_buffer.put.call_count == 200 - 79, cam.shared_buffer.put.call_count

        # Between the two marks the camera stays dark and keeps re-sending, so a display that reconnects sees it again
        messages = []
        cam = camera(iter([dark] * 100 + [dark, light] * 300), messages)
        run(cam, 700, now)
        assert cam.too_dark and sum(m.startswith("ERROR") for m in messages) == 2, messages  # the second 30 s in, half dark

        # A region that no longer fits (the camera now sends a smaller picture) is reported at the same pace, never crashes
        messages = []
        cam = camera(iter([light] * 400), messages, roi=[[0, 0], [1280, 0], [1280, 720], [0, 720]])
        run(cam, 400, now)
        assert messages == ["ERROR maingate_entry_cctv-camera-1: Region of interest does not fit the 640x360 camera picture. Redraw it in the ROI page."] * 2, messages
        assert not cam.shared_buffer.put.called
    print(f"camera ok (regions checked and judged on their own pixels, {len(alerts)} alerts for 500 dark frames, "
          "recovery announced once, dark frames held back before the window fills, re-sent while dark)")


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


def test_ifr_client_reconnects():
    """A consumer thread keeps one InsightFace client; after a connection error it must drop its session for a new one."""
    import requests
    from insightface_face_detection import IFRClient
    client = IFRClient(host="http://127.0.0.1", port="9")  # nothing listens on port 9
    before = client.session
    try:
        client.extract(["x"])
    except requests.ConnectionError:
        pass
    else:
        raise AssertionError("expected a connection error")
    assert client.session is not before, "session kept after a connection error"
    print("InsightFace client ok (new session after a connection error)")


if __name__ == "__main__":
    test()
    test_decoders()
    test_ifr_client_reconnects()
