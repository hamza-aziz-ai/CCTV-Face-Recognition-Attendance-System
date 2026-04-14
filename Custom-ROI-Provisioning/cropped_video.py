import os
import cv2

def resize_roi_to_area(roi_frame, target_area=1280*720):
    """
    Resize a ROI to have approximately the target area (number of pixels)
    without changing its aspect ratio.

    Parameters:
      roi_frame (numpy.ndarray): The cropped ROI image.
      target_area (int): The desired number of pixels (default is 921600).

    Returns:
      numpy.ndarray: The resized ROI image.
    """
    # Get the current dimensions of the ROI
    original_height, original_width = roi_frame.shape[:2]
    current_area = original_width * original_height

    # Compute the scale factor to achieve the target area
    scale_factor = (target_area / current_area) ** 0.5

    # Calculate the new dimensions while preserving aspect ratio
    new_width = int(round(original_width * scale_factor))
    new_height = int(round(original_height * scale_factor))

    print(f"Original dimensions: {original_width}x{original_height} (area = {current_area})")
    print(f"Scale factor: {scale_factor:.4f}")
    print(f"New dimensions: {new_width}x{new_height} (approximate area = {new_width * new_height})")

    # Resize the ROI using the computed dimensions
    resized_roi = cv2.resize(roi_frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
    return resized_roi


def main():
    # Initialize the camera (0 is typically the default camera)
    cap = cv2.VideoCapture(os.environ.get("RTSP_URL", ""))

    # Define the ROI coordinates
    # (x, y) is the top-left corner,
    # w is the width, h is the height of the rectangle
    x_min, y_min, x_max, y_max = 660, 0, 1824, 1438

    # Print rectangle coordinates
    # print(f"Rectangle coordinates and size: x={x}, y={y}, width={w}, height={h}")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # frame = frame[y_min:y_max, x_min:x_max]

        # Draw the rectangle on the frame
        # cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), (0, 255, 0), 2)

        # Show the live frame with the drawn rectangle
        # cv2.imshow("Full Frame with ROI", frame)

        # Crop (slice) the frame to the ROI
        roi_frame = frame[y_min:y_max, x_min:x_max]
        print(roi_frame.shape, roi_frame.shape[0]*roi_frame.shape[1])
        resized_roi = resize_roi_to_area(roi_frame)
        print(resized_roi.shape, resized_roi.shape[0]*resized_roi.shape[1])

        # Display the ROI in a separate window
        cv2.imshow("Cropped ROI", resized_roi)

        # Press 'q' to exit
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
