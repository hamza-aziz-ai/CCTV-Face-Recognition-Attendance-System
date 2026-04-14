import os
import cv2
import numpy as np
from typing import List
import urllib.parse

# Check OpenCV version for compatibility
print(f"OpenCV version: {cv2.__version__}")

class RTSPROIExtractor:
    def __init__(self, rtsp_url: str):
        self.rtsp_url = rtsp_url
        self.polygon_points = []
        self.drawing = False
        self.frame = None
        self.original_frame = None
        self.display_frame = None
        self.roi_coordinates = []
        self.current_mouse_pos = (0, 0)

    def mouse_callback(self, event, x, y, flags, param):
        """Mouse callback function to handle polygon drawing"""
        # Update current mouse position for live preview
        self.current_mouse_pos = (x, y)

        if event == cv2.EVENT_LBUTTONDOWN:
            # Add point to polygon
            self.polygon_points.append([x, y])
            print(f"Point added: ({x}, {y})")

            # Redraw the frame with all points and lines
            self.update_display_frame()

        elif event == cv2.EVENT_RBUTTONDOWN:
            # Right click to close polygon and extract ROI
            if len(self.polygon_points) >= 3:
                self.close_polygon_and_extract_roi()

        elif event == cv2.EVENT_MOUSEMOVE:
            # Update display with live preview line
            self.update_display_frame()

    def update_display_frame(self):
        """Update the display frame with polygon points and live preview"""
        # Start with original frame
        self.display_frame = self.frame.copy()

        # Draw all existing points
        for i, point in enumerate(self.polygon_points):
            cv2.circle(self.display_frame, tuple(point), 5, (0, 255, 0), -1)

            # Add point number text
            cv2.putText(self.display_frame, str(i+1),
                        (point[0] + 10, point[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        # Draw lines between consecutive points
        for i in range(len(self.polygon_points) - 1):
            cv2.line(self.display_frame,
                     tuple(self.polygon_points[i]),
                     tuple(self.polygon_points[i + 1]),
                     (0, 255, 0), 2)

        # Draw live preview line from last point to current mouse position
        if len(self.polygon_points) > 0:
            cv2.line(self.display_frame,
                     tuple(self.polygon_points[-1]),
                     self.current_mouse_pos,
                     (0, 255, 255), 2)  # Yellow dashed-like line

            # Draw preview line to first point if we have 3+ points (to show polygon closure)
            if len(self.polygon_points) >= 3:
                cv2.line(self.display_frame,
                         self.current_mouse_pos,
                         tuple(self.polygon_points[0]),
                         (255, 255, 0), 2)  # Cyan line for closure preview

        # Add instruction text
        instruction_text = f"Points: {len(self.polygon_points)} | Left click: Add point | Right click: Close polygon"
        cv2.putText(self.display_frame, instruction_text,
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(self.display_frame, instruction_text,
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)

        # Show current mouse coordinates
        coord_text = f"Mouse: ({self.current_mouse_pos[0]}, {self.current_mouse_pos[1]})"
        cv2.putText(self.display_frame, coord_text,
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        cv2.putText(self.display_frame, coord_text,
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 100, 200), 1)

        cv2.imshow('RTSP Stream - Draw ROI Polygon', self.display_frame)

    def close_polygon_and_extract_roi(self):
        """Close the polygon and extract ROI"""
        # Create final display frame with closed polygon
        self.display_frame = self.frame.copy()

        # Draw all points and lines
        for i, point in enumerate(self.polygon_points):
            cv2.circle(self.display_frame, tuple(point), 5, (0, 255, 0), -1)

        # Draw all lines including closing line
        for i in range(len(self.polygon_points)):
            start_point = self.polygon_points[i]
            end_point = self.polygon_points[(i + 1) % len(self.polygon_points)]
            cv2.line(self.display_frame, tuple(start_point), tuple(end_point), (0, 255, 0), 2)

        # Fill the polygon with semi-transparent overlay
        pts = np.array(self.polygon_points, np.int32)
        overlay = self.display_frame.copy()
        cv2.fillPoly(overlay, [pts], (0, 255, 0))
        cv2.addWeighted(overlay, 0.3, self.display_frame, 0.7, 0, self.display_frame)

        # Store ROI coordinates
        self.roi_coordinates = self.polygon_points.copy()

        # Create mask for ROI extraction
        mask = np.zeros(self.original_frame.shape[:2], dtype=np.uint8)
        cv2.fillPoly(mask, [pts], 255)

        # Extract ROI
        roi = cv2.bitwise_and(self.original_frame, self.original_frame, mask=mask)

        # Get bounding rectangle for cropping
        x, y, w, h = cv2.boundingRect(pts)
        cropped_roi = roi[y:y+h, x:x+w]
        cropped_mask = mask[y:y+h, x:x+w]

        # Apply mask to cropped ROI
        cropped_roi[cropped_mask == 0] = [0, 0, 0]

        # Display results
        cv2.imshow('ROI Extracted', cropped_roi)
        cv2.imshow('RTSP Stream - Draw ROI Polygon', self.display_frame)

        # Print ROI coordinates
        print("\n" + "="*50)
        print("ROI COORDINATES:")
        print("="*50)
        print(f"Polygon Points: {self.roi_coordinates}")
        print(f"Bounding Rectangle: x={x}, y={y}, width={w}, height={h}")
        print("="*50)

    def reset_polygon(self):
        """Reset the polygon points and frame"""
        self.polygon_points = []
        self.roi_coordinates = []
        self.current_mouse_pos = (0, 0)
        if self.original_frame is not None:
            self.frame = self.original_frame.copy()
            self.display_frame = self.frame.copy()
            cv2.imshow('RTSP Stream - Draw ROI Polygon', self.display_frame)

    def run(self):
        """Main function to run the RTSP ROI extractor"""
        print("Starting RTSP ROI Extractor...")
        print("Instructions:")
        print("- Left click to add polygon points")
        print("- Right click to close polygon and extract ROI")
        print("- Press 'r' to reset polygon")
        print("- Press 'c' to capture current frame")
        print("- Press 'q' to quit")
        print("- Press 's' to save ROI coordinates to file")
        print()

        # Initialize video capture with error handling
        try:
            cap = cv2.VideoCapture(self.rtsp_url)
        except Exception as e:
            print(f"Error initializing video capture: {e}")
            return

        if not cap.isOpened():
            print(f"Error: Unable to open RTSP stream: {self.rtsp_url}")
            print("Please check:")
            print("1. RTSP URL is correct")
            print("2. Camera is accessible")
            print("3. Network connection is stable")
            print("4. Username/password are correct (if required)")
            return

        # Set buffer size to reduce latency (if supported)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass  # Some cameras don't support this property

        # Create window and set mouse callback
        try:
            cv2.namedWindow('RTSP Stream - Draw ROI Polygon', cv2.WINDOW_AUTOSIZE)
        except AttributeError:
            cv2.namedWindow('RTSP Stream - Draw ROI Polygon')

        cv2.setMouseCallback('RTSP Stream - Draw ROI Polygon', self.mouse_callback)

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("Error: Failed to grab frame from RTSP stream")
                    break

                # Store original frame and working frame
                if len(self.polygon_points) == 0:
                    self.original_frame = frame.copy()
                    self.frame = frame.copy()
                    self.display_frame = frame.copy()

                # Display frame (only if no polygon is being drawn to avoid flickering)
                if len(self.polygon_points) == 0:
                    cv2.imshow('RTSP Stream - Draw ROI Polygon', self.frame)

                # Handle key presses
                key = cv2.waitKey(1) & 0xFF

                if key == ord('q'):
                    break
                elif key == ord('r'):
                    self.reset_polygon()
                    print("Polygon reset")
                elif key == ord('c'):
                    # Capture current frame for polygon drawing
                    self.original_frame = frame.copy()
                    self.frame = frame.copy()
                    self.display_frame = frame.copy()
                    self.polygon_points = []
                    self.roi_coordinates = []
                    self.current_mouse_pos = (0, 0)
                    cv2.imshow('RTSP Stream - Draw ROI Polygon', self.display_frame)
                    print("Frame captured for polygon drawing")
                elif key == ord('s'):
                    if self.roi_coordinates:
                        self.save_coordinates_to_file()
                    else:
                        print("No ROI coordinates to save. Draw a polygon first.")

        except KeyboardInterrupt:
            print("\nInterrupted by user")

        finally:
            cap.release()
            cv2.destroyAllWindows()
            print("RTSP ROI Extractor closed")

    def save_coordinates_to_file(self):
        """Save ROI coordinates to a text file"""
        try:
            with open('roi_coordinates.txt', 'w') as f:
                f.write("ROI Polygon Coordinates:\n")
                f.write("="*30 + "\n")
                f.write(f"Points: {self.roi_coordinates}\n")
                f.write("\nPython List Format:\n")
                f.write(f"roi_coordinates = {self.roi_coordinates}\n")
            print("ROI coordinates saved to 'roi_coordinates.txt'")
        except Exception as e:
            print(f"Error saving coordinates: {e}")

    def get_roi_coordinates(self) -> List[List[int]]:
        """Return the ROI coordinates as List[List[int]]"""
        return self.roi_coordinates


def main():
    # RTSP URL - Replace with your actual RTSP stream URL
    # Examples:

    # For testing with webcam, use index 0
    rtsp_url = os.environ.get("RTSP_URL", "")  # e.g. rtsp://USER:PASS@CAMERA_IP:554/Streaming/Channels/101

    # Create and run the ROI extractor
    extractor = RTSPROIExtractor(rtsp_url)
    extractor.run()

    # Print final coordinates
    final_coordinates = extractor.get_roi_coordinates()
    if final_coordinates:
        print(f"\nFinal ROI Coordinates: {final_coordinates}")
        print(f"Data type: {type(final_coordinates)}")
    else:
        print("No ROI was defined")


if __name__ == "__main__":
    main()
