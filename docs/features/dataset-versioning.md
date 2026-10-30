# Feature: dataset and embedding versioning

**Goal:** know exactly which images, model and settings produced the vectors in Milvus, and be able to roll back.

**Status:** the DVC remote is built (D-019). The rest is proposed, not started.

## Design

1. Images stay in DVC, on the dataset store. They are the source; vectors are derived from them.
2. Vectors move from pickle to Parquet: `person_id`, `image_path`, `image_md5`, `embedding`, `model_md5`, detector settings, `created_at`. Stored outside the dataset folder, named by dataset version, model and settings.
3. One Milvus collection per embedding version, behind an alias such as `FACES_ACTIVE`. Build, check, then switch the alias. Rollback is pointing it back.
4. The model manifest records dataset hash, Parquet hash, model md5 and collection name, and CI checks for drift.

Rejected for now: Lance (versioned tables with built-in vector search), because it adds a storage format this size does not need.

## Open

- Migrate the datasets from Google Drive: `dvc pull -r face-recognition-dataset-gdrive`, then `dvc push -r minio`, on a machine with that remote.
- Set `DATASET_STORE_*` in `.env` and start the store.
- A deletion path for one person across images, Parquet and Milvus, plus a retention policy for DVC history.

## Log

- 2026-10-30: design agreed in discussion; MinIO chosen as the remote; DVC push and pull tested on a throwaway instance.
