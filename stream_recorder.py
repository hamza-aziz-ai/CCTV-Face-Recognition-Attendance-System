import os
import cv2
import time

# RTSP stream URL of your IP camera
rtsp_url = os.environ.get("RTSP_URL", "")

# Define the output file name and codec
output_file = 'cam-5.avi'
fourcc = cv2.VideoWriter_fourcc(*'XVID')
fps = 25.0  # Adjust as needed
frame_size = (2560, 1440)  # Update based on your camera's resolution

# Open the RTSP stream
cap = cv2.VideoCapture(rtsp_url)

# Check if the stream is opened successfully
if not cap.isOpened():
    print("Error: Cannot open RTSP stream.")
    exit()

# Get the frame width and height from the camera
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
frame_size = (width, height)

# Initialize the video writer
out = cv2.VideoWriter(output_file, fourcc, fps, frame_size)

print("Recording started... Press Ctrl+C to stop.")

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to retrieve frame. Retrying...")
            time.sleep(1)
            continue

        # Write the frame to the output file
        out.write(frame)

        # Optional: Show the frame (comment out if not needed)
        # cv2.imshow('Recording', frame)
        # if cv2.waitKey(1) & 0xFF == ord('q'):
        #     break

except KeyboardInterrupt:
    print("Recording stopped by user.")

finally:
    # Release everything
    cap.release()
    out.release()
    cv2.destroyAllWindows()
    print("Resources released. File saved:", output_file)
