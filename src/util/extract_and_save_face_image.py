import os
import sys
import cv2

# Relative issue - https://www.geeksforgeeks.org/python-import-from-parent-directory/
current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from insightface_face_detection import IFRClient  # Adjust import based on your client file location
from parameters import DISPLAY_FACE_IMAGE_PATH, FACIAL_RECOGNITION_DATASET_PATH


# Initialize the IFRClient
client = IFRClient()


def extract_faces_from_image(image_path, margin=0.4, target_size=1024):
    """Extract faces from a single image using the IFRClient."""
    image = cv2.imread(image_path)
    if image is None:
        return []

    # Convert image to list of frames (just one frame in this case)
    faces_data = client.extract_face_data([image], mode='data', threshold=0.6, extract_embeddings=True,
                                          return_face_data=True)

    faces = []
    if faces_data and faces_data.get('data'):
        for face_data in faces_data['data']:
            if face_data.get('status') == 'ok':
                for face in face_data.get('faces', []):
                    bbox = face.get('bbox', [])
                    if bbox:
                        x_min, y_min, x_max, y_max = bbox
                        # Adjust bounding box with margin
                        width = x_max - x_min
                        height = y_max - y_min
                        margin_x = int(margin * width)
                        margin_y = int(margin * height)

                        x_min = max(0, x_min - margin_x)
                        y_min = max(0, y_min - margin_y)
                        x_max = min(image.shape[1], x_max + margin_x)
                        y_max = min(image.shape[0], y_max + margin_y)

                        # Ensure the bounding box is square
                        box_width = x_max - x_min
                        box_height = y_max - y_min
                        max_side = max(box_width, box_height)
                        center_x = x_min + box_width // 2
                        center_y = y_min + box_height // 2

                        x_min = max(0, center_x - max_side // 2)
                        y_min = max(0, center_y - max_side // 2)
                        x_max = min(image.shape[1], center_x + max_side // 2)
                        y_max = min(image.shape[0], center_y + max_side // 2)

                        # Crop face from image
                        face_img = image[y_min:y_max, x_min:x_max]
                        # Resize to target size
                        face_img = cv2.resize(face_img, (target_size, target_size))
                        faces.append(face_img)

    return faces


def process_dataset(dataset_path, output_path, margin=0.4, target_size=1024):
    """Process the entire dataset to extract and save faces."""
    for folder in os.listdir(dataset_path):
        folder_path = os.path.join(dataset_path, folder)
        if not os.path.isdir(folder_path):
            continue

        images = [os.path.join(folder_path, img) for img in os.listdir(folder_path) if img.lower().endswith('.jpg') or img.lower().endswith('.jpeg') or img.lower().endswith('.png')]
        if not images:
            continue

        # Sort images by timestamp (filename) to find the earliest
        images.sort()
        earliest_image_path = images[0]

        faces = extract_faces_from_image(earliest_image_path, margin, target_size)
        if not faces:
            print(f"No faces detected in {earliest_image_path}")
            continue

        # Create output directory
        output_folder = os.path.join(output_path, folder)
        os.makedirs(output_folder, exist_ok=True)

        # Save the first detected face (front face)
        front_face_path = os.path.join(output_folder, 'front_face.jpg')
        cv2.imwrite(front_face_path, faces[0])
        print(f"Saved front face to {front_face_path}")


if __name__ == "__main__":
    # Usage: python3 src/util/extract_and_save_face_image.py <dataset_folder>
    process_dataset(sys.argv[1], DISPLAY_FACE_IMAGE_PATH)
