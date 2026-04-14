import os
import psycopg2

# Adjust these as needed:
DB_HOST = os.environ.get("POSTGRES_HOST", "localhost")
DB_NAME = "ABESIT_Face_Recognition_Database"
DB_USER = os.environ.get("POSTGRES_USER")
DB_PASS = os.environ.get("POSTGRES_PASSWORD")

# Path to the root of your dataset folder:
ROOT_DIR = "/home/hamza/CCTV-Face-Recognition-Attendance-System/FACIAL-RECOGNITION-DATASET/ABESIT"

# Directories within ROOT_DIR to process (ignoring FACE_EMBEDDINGS).
# Typically these might be:
DATASET_DIRS = [
    "GRIL-MEMBERS_DATASET"
]

def main():
    connection = psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS
    )
    cursor = connection.cursor()

    for dataset_dir in DATASET_DIRS:
        dataset_path = os.path.join(ROOT_DIR, dataset_dir)
        
        if not os.path.isdir(dataset_path):
            # If the directory isn't found, skip
            continue
        
        # Each subdirectory here is an admission_number (e.g., EATAI1714 or 2021BPH001)
        for admission_number in os.listdir(dataset_path):
            subdir_path = os.path.join(dataset_path, admission_number)
            
            # Skip if not a directory
            if not os.path.isdir(subdir_path):
                continue

            # 1) Insert/Upsert the individual
            # Since "admission_number" has a unique constraint, use ON CONFLICT DO NOTHING
            insert_individual_sql = """
                INSERT INTO individuals (admission_number)
                VALUES (%s)
                ON CONFLICT (admission_number)
                DO NOTHING
            """
            cursor.execute(insert_individual_sql, (admission_number,))

            # 2) For each image in that folder, insert a face_images record
            for filename in os.listdir(subdir_path):
                # Simple check for image extension
                if filename.lower().endswith((".jpg", ".jpeg", ".png")):
                    image_full_path = os.path.abspath(os.path.join(subdir_path, filename))

                    with open(image_full_path, 'rb') as f:
                        image_bytes = f.read()

                    insert_face_image_sql = """
                        INSERT INTO face_images
                            (admission_number, validated, review_comments, image_path, image_data)
                        VALUES
                            (%s, %s, %s, %s, %s)
                        ON CONFLICT (admission_number, image_path) DO NOTHING;
                    """
                    cursor.execute(insert_face_image_sql, (
                        admission_number,
                        True,
                        "Manually Captured Image",
                        image_full_path,
                        psycopg2.Binary(image_bytes)
                    ))
    
    # Commit changes
    connection.commit()
    cursor.close()
    connection.close()

if __name__ == "__main__":
    main()
