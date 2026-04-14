import os
from PIL import Image

def convert_to_png(directory):
    """
    Traverse the directory and subdirectories to convert invalid JPEG images to PNG format.
    """
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            if file.lower().endswith(('.jpg', '.jpeg')):  # Check for JPEG files
                try:
                    # Attempt to open the image
                    with Image.open(file_path) as img:
                        img.load()  # Force loading of the image to detect issues
                        print(f"Valid JPEG: {file_path}")
                except Exception as e:
                    # If an error occurs, attempt conversion to PNG
                    print(f"Invalid JPEG detected ({file_path}): {e}")
                    try:
                        with Image.open(file_path) as img:
                            # Convert to RGB to ensure compatibility for saving as PNG
                            img = img.convert("RGB")
                            # Save as PNG
                            png_path = os.path.splitext(file_path)[0] + ".png"
                            img.save(png_path, "PNG")
                            print(f"Converted to PNG: {png_path}")
                            os.remove(file_path)  # Optionally remove the original invalid JPEG
                    except Exception as e2:
                        print(f"Failed to convert {file_path}: {e2}")


if __name__ == "__main__":
    # Specify the directory to process
    directory = "FACIAL_RECOGNITION_DATASET/STUDENT_DATASET/CURRENTLY_ENROLLED_BATCH/BATCH_2023"
    convert_to_png(directory)
