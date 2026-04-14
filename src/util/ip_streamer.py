"""
This module acts as a relay streamer that broadcasts video streams from two local video sources
to clients over the internet. Each video source has 5 network streams running in parallel.

ngrok utility is used to map the local IP camera to a public URL.

For more information on ngrok, visit https://ngrok.com/

Author: Anubhav Patrick
Date: 2023-03-19
"""

import argparse
import cv2
import time
from flask import Flask, Response

# Create a Flask app instance
app = Flask(__name__)

# secret key for the session
app.config['SECRET_KEY'] = 'ip_cam_streamer'

# Set the video paths (local video files or IP camera URLs)
VIDEO_PATH_1 = "src/test_videos/Left_28August2023.mp4"
VIDEO_PATH_2 = "src/test_videos/Right_28August2023.mp4"


def video_feed(video_path, stream_id):
    # Open the video file
    cap = cv2.VideoCapture(video_path)

    # Initialize the stream
    print(f'Initializing camera stream {stream_id}...')
    while True:
        ret, _ = cap.read()
        if ret:
            print(f'Initialized stream {stream_id}!')
            break

    # tick = time.time()
    # frame_count = 0
    while True:
        # Read a frame from the video
        ret, frame = cap.read()

        # If video is at the end, reset to the start
        if not ret:
            print(f"Stream {stream_id} reached end. Restarting...")
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()

        frame = cv2.resize(frame, (2 * 640, 2 * 360))

        # frame_count += 1
        # tock = time.time()
        # time_taken = tock - tick

        # if time_taken > 0:
        #     fps = frame_count / time_taken
        #     print(f'FPS (Stream {stream_id}): {fps:.3f}')
        #     tick = time.time()
        #     frame_count = 0

        if ret:
            # Yield the frame as a response to the client
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + cv2.imencode('.jpg', frame)[1].tobytes() + b'\r\n')


@app.route('/video1/<int:stream_id>')
def stream_1(stream_id):
    return Response(video_feed(VIDEO_PATH_1, stream_id), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/video2/<int:stream_id>')
def stream_2(stream_id):
    return Response(video_feed(VIDEO_PATH_2, stream_id), mimetype='multipart/x-mixed-replace; boundary=frame')


# Run the Flask app
if __name__ == '__main__':

    # Read run-time parameters from the command line - host and port
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--app', type=str, default='0.0.0.0', help='Host app IP address')
    parser.add_argument('-p', '--port', type=int, default=5010, help='Port number of the app')

    args = parser.parse_args()

    # # Update VIDEO_PATH based on command-line input
    # VIDEO_PATH = args.cam_ip
    # if VIDEO_PATH == '0':
    #     VIDEO_PATH = int(VIDEO_PATH)

    # Start Flask app
    app.run(host=args.app, port=args.port)
