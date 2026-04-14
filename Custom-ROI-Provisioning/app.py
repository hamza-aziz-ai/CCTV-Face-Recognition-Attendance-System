"""
This module was created to update the ROI (region of interest) for each IP camera.

Author: Kshitij Parashar
Date: 4 October 2023
"""

from flask import Flask, render_template, Response, request, send_from_directory, redirect, url_for
import cv2
import fileinput

from src.util.generic_utilities import create_mask, roi_coordinates
from src.parameters import IP_CAMS, FRAME_WIDTH, FRAME_HEIGHT

app = Flask(__name__)
camera_name = ''  # Initialize with an empty string

# Initialize variables for the text boxes
width = ''
height = ''
pos_x = ''
pos_y = ''


# Function to capture video from the IP camera
def get_camera_feed():
    global camera_name
    if camera_name:
        cap = cv2.VideoCapture(IP_CAMS[camera_name][0])
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            else:
                frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
                roi_left, roi_top, roi_right, roi_bottom = roi_coordinates(int(width), int(
                    height), frame.shape[1], frame.shape[0], int(pos_x), int(pos_y))
                mask = create_mask(frame, roi_left, roi_top,
                                   roi_right, roi_bottom)
                frame = frame * mask

                _, buffer = cv2.imencode('.jpg', frame)
                frame = buffer.tobytes()

                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        cap.release()


@app.route('/', methods=['GET', 'POST'])
def index():
    global camera_name, width, height, pos_x, pos_y
    if request.method == 'POST':
        camera_name = request.form['camera_name']

        # Get values from the text boxes and store them in variables
        width = request.form['width']
        height = request.form['height']
        pos_x = request.form['pos_x']
        pos_y = request.form['pos_y']

    return render_template('index.html', width=width, height=height, pos_x=pos_x, pos_y=pos_y)


# Serve static files (JavaScript)


@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)


@app.route('/video_feed')
def video_feed():
    return Response(get_camera_feed(), mimetype='multipart/x-mixed-replace; boundary=frame')


# Route to send variables to Python file
@app.route('/send_variables', methods=['POST'])
def update_variables():
    # Get the final details and update them in parameters.py
    new_values = (int(width), int(height), int(pos_x), int(pos_y))
    with fileinput.FileInput("src/parameters.py", inplace=True) as file:
        for line in file:
            # Search for the line that corresponds to the key
            if camera_name in line:
                if "# " in line:
                    # Replace the line with the updated values
                    line = f'    # "{camera_name}": ["{IP_CAMS[camera_name][0]}", {new_values}],\n'
                else:
                    line = f'    "{camera_name}": ["{IP_CAMS[camera_name][0]}", {new_values}],\n'
            print(line, end='')

    # Redirect back to the main page with a success message
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
