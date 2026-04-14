import os
import cv2
import base64
import json
from openpyxl import Workbook
from src.insightface_face_detection import IFRClient
from parameters import INSIGHTFACE_HOST, INSIGHTFACE_PORT

# Initialize the InsightFace REST API client
insightface_client = IFRClient(host=INSIGHTFACE_HOST, port=INSIGHTFACE_PORT)

def get_orientation(landmarks):
    """
    Determines the orientation of a face based on its landmarks.

    Args:
        landmarks (list): A list of 5 (x, y) landmark points.

    Returns:
        str: Orientation of the face - "correct" or "incorrect".
    """
    left_eye_y, right_eye_y = landmarks[0][1], landmarks[1][1]
    nose_y = landmarks[2][1]
    left_mouth_y, right_mouth_y = landmarks[3][1], landmarks[4][1]

    if left_eye_y < nose_y < left_mouth_y and right_eye_y < nose_y < right_mouth_y:
        return "correct"

    return "incorrect"

def correct_orientation(image_path):
    """
    Corrects the orientation of a face image using InsightFace-REST API.

    Args:
        image_path (str): Path to the input image.

    Returns:
        bool: True if orientation was corrected, False otherwise.
    """
    img = cv2.imread(image_path)
    if img is None:
        return False, "Failed to load image"

    _, buffer = cv2.imencode(".jpg", img)
    base64_data = base64.b64encode(buffer.tobytes()).decode('ascii')

    faces_data = insightface_client.extract(
        data=[base64_data],
        mode='data',
        use_msgpack=True,
        return_landmarks=True
    )

    single_face_data = faces_data['data'][0]['faces']
    if not single_face_data:
        return False, "No face detected"

    landmarks = single_face_data[0]["landmarks"]
    orientation = get_orientation(landmarks)

    if orientation != "correct":
        img = cv2.rotate(img, cv2.ROTATE_180)
        cv2.imwrite(image_path, img)
        return True, "Corrected"

    return True, "Already Correct"

if __name__ == "__main__":
    dataset_path = "FACIAL_RECOGNITION_DATASET/FACULTY-STAFF-EMPLOYEE_DATASET"
    report = {
        "directories": [],
        "summary": {
            "total_directories": 0,
            "invalid_directories": 0,
            "total_photos": 0,
            "already_correct_photos": 0,
            "corrected_photos": 0,
            "uncorrected_photos": 0
        }
    }

    for sub_directory in os.listdir(dataset_path):
        sub_dir_path = os.path.join(dataset_path, sub_directory)
        if not os.path.isdir(sub_dir_path):
            continue

        report["summary"]["total_directories"] += 1
        directory_info = {
            "directory": sub_directory,
            "photo_count": 0,
            "invalid": False,
            "already_correct_photos": [],
            "corrected_photos": [],
            "uncorrected_photos": [],
            "unreadable_photos": []
        }

        photos = os.listdir(sub_dir_path)
        directory_info["photo_count"] = len(photos)
        report["summary"]["total_photos"] += len(photos)

        if len(photos) not in [5, 10]:
            directory_info["invalid"] = True
            report["summary"]["invalid_directories"] += 1

        for photo in photos:
            photo_path = os.path.join(sub_dir_path, photo)
            success, reason = correct_orientation(photo_path)

            if not success and reason == "Failed to load image":
                directory_info["unreadable_photos"].append(photo)
            elif success and reason == "Corrected":
                directory_info["corrected_photos"].append(photo)
                report["summary"]["corrected_photos"] += 1
            elif success and reason == "Already Correct":
                directory_info["already_correct_photos"].append(photo)
                report["summary"]["already_correct_photos"] += 1
            elif not success:
                directory_info["uncorrected_photos"].append(photo)
                report["summary"]["uncorrected_photos"] += 1

        report["directories"].append(directory_info)

    # Save JSON report
    json_report_path = os.path.join(dataset_path, "faculty-staff-employee.json")
    with open(json_report_path, "w") as json_file:
        json.dump(report, json_file, indent=4)

    # Save Excel report
    excel_report_path = os.path.join(dataset_path, "faculty-staff-employee.xlsx")
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Dataset Report"

    # Add headers
    sheet.append([
        "Directory", "Photo Count", "Invalid Directory", "Already Correct Photos Count", "Corrected Photos Count",
        "Uncorrected Photos Count", "Unreadable Photos Count"
    ])

    for directory in report["directories"]:
        sheet.append([
            directory["directory"],
            directory["photo_count"],
            "Yes" if directory["invalid"] else "No",
            len(directory["already_correct_photos"]),
            len(directory["corrected_photos"]),
            len(directory["uncorrected_photos"]),
            len(directory["unreadable_photos"])
        ])

    # Add summary at the end
    sheet.append([])  # Blank row
    sheet.append(["Summary"])
    sheet.append(["Total Directories", report["summary"]["total_directories"]])
    sheet.append(["Invalid Directories", report["summary"]["invalid_directories"]])
    sheet.append(["Total Photos", report["summary"]["total_photos"]])
    sheet.append(["Already Correct Photos", report["summary"]["already_correct_photos"]])
    sheet.append(["Corrected Photos", report["summary"]["corrected_photos"]])
    sheet.append(["Uncorrected Photos", report["summary"]["uncorrected_photos"]])

    workbook.save(excel_report_path)

    print(f"Reports saved: \nJSON: {json_report_path}\nExcel: {excel_report_path}")
