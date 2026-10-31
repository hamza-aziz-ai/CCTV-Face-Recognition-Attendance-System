# Feature: dataset and embedding versioning

**Goal:** know exactly which images, model and settings produced the vectors in Milvus, and be able to roll back.

**Status:** photos are versioned in DVC on the dataset store, and enrolment is checked (D-019, D-026). Vectors are versioned with the photos and served through an alias (D-030), which covers steps 2 and 3 in a simpler form. Step 4, lineage, is not started.

## Design

1. Images stay in DVC, on the dataset store. They are the source; vectors are derived from them.
2. Vectors move from pickle to Parquet: `person_id`, `image_path`, `image_md5`, `embedding`, `model_md5`, detector settings, `created_at`. Stored outside the dataset folder, named by dataset version, model and settings.
3. One Milvus collection per embedding version, behind an alias such as `FACES_ACTIVE`. Build, check, then switch the alias. Rollback is pointing it back.
4. The model manifest records dataset hash, Parquet hash, model md5 and collection name, and CI checks for drift.

Rejected for now: Lance (versioned tables with built-in vector search), because it adds a storage format this size does not need.

## Open

- A deletion path for one person across images, Parquet and Milvus, plus a retention policy for DVC history.

## Log

- 2026-10-30: design agreed in discussion; MinIO chosen as the remote; DVC push and pull tested on a throwaway instance.
- 2026-10-31: D-030 built steps 2 and 3: `vectors.parquet` in each person's folder instead of a separate file, and the existing collection name as the alias. Tested on throwaway collections; the live collection waits for the owner's `migrate`.
- 2026-10-30: the original datasets stayed with the owner's previous employer and cannot be recovered, so versioning starts fresh. `hamza_aziz` is the first real person: 10 photos pushed, then restored identically by `dvc pull`.
