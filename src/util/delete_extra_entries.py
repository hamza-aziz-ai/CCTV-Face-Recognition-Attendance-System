import json
import sys
import os
from src.dynamic_face_data_collector.postgresql_database_handler import delete_face_data

PERSON_ID = sys.argv[1]  # usage: python delete_extra_entries.py <PERSON_ID>
CLUSTER_NAME = "cluster-1"
BASE_PATH = "DYNAMIC-FACIAL-RECOGNITION-DATASET/ABESIT"

# 1. Load existing metadata
with open(f"{BASE_PATH}/{PERSON_ID}/{CLUSTER_NAME}/meta.json") as f:
    metadata = json.load(f)

# 2. Sort descending by pupil_distance, match_score
sorted_metadata = sorted(
    metadata,
    key=lambda x: (x["pupil_distance"], x["match_score"]),
    reverse=True
)

# 3. Split
NUMBER_OF_PICTURES = 3
keepers = sorted_metadata[:NUMBER_OF_PICTURES]
pruned = sorted_metadata[NUMBER_OF_PICTURES:]

# 4. Overwrite meta.json with top 3
with open(f"{BASE_PATH}/{PERSON_ID}/{CLUSTER_NAME}/meta.json", "w") as f:
    json.dump(keepers, f, indent=4)

pruned_filepaths = [
    os.path.join(BASE_PATH, PERSON_ID, CLUSTER_NAME, entry["filename"])
    for entry in pruned
]

# 6. Save file paths to delete
with open(f"{BASE_PATH}/{PERSON_ID}/{CLUSTER_NAME}/pruned_images_to_delete.txt", "w") as f:
    for path in pruned_filepaths:
        f.write(path + "\n")

# 7. Save pruned metadata for DB cleanup
with open(f"{BASE_PATH}/{PERSON_ID}/{CLUSTER_NAME}/pruned_metadata.json", "w") as f:
    json.dump(pruned, f, indent=4)

with open(f"{BASE_PATH}/{PERSON_ID}/{CLUSTER_NAME}/pruned_metadata.json") as f:
    entries = json.load(f)

for entry in entries:
    filename = entry["filename"]
    full_path = os.path.join(BASE_PATH, PERSON_ID, CLUSTER_NAME, filename)

    # Delete file
    try:
        os.remove(full_path)
        print(f"Deleted file: {full_path}")
    except FileNotFoundError:
        print(f"File not found, skipping: {full_path}")
    except Exception as e:
        print(f"Error deleting file {full_path}: {e}")

    # Delete from DB
    try:
        delete_face_data(PERSON_ID, full_path, CLUSTER_NAME)
        print(f"Deleted DB record for: {full_path}")
    except Exception as e:
        print(f"Error deleting from DB: {e}")