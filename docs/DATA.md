# Data

The system stores biometric data in all the places below. A deletion request has to reach every one of them, and no code does that yet.

| Structure | Shape | Access | Size | Writes | Reads | Trade-off |
|---|---|---|---|---|---|---|
| Milvus primary collection `FACE_DATA_COLLECTION_FOR_COSINE` | `name_id` (VARCHAR 60, primary key), `embeddings` (512 float) | Top 5 by cosine, `GPU_IVF_FLAT`, nlist 128, nprobe 10 | One row per enrolled photo: 10 today | `src/util/enrol_person.py`, or `upload_embeddings.py` for a whole pickle | Consumer | Fast approximate search, at the cost of GPU memory and possible misses |
| Milvus staging collection `FACE_DATA_STAGING_COLLECTION_FOR_COSINE` | Same | Same | Grows nightly | Nightly updater | Consumer | Adapts to current appearance, but a bad crop can poison matches |
| `recognition_results` in `CCTV_Camera_Surveillance` | Person, camera, time, annotated frame | Insert per recognition; reads by date and location | Grows with frames | DB controller | Reporting API | Partitioned by year and location, so reports stay fast; frames make it large |
| `person_summary`, `face_images` in `Face_Recognition_Database` | Per-person metadata and crop records | By person | Grows | Face collector | Nightly updater | Tracks which crops are processed |
| `multiprocessing.Queue` | Frames with camera metadata | FIFO | Unbounded, in memory | Camera threads | Recognition workers | Simplest hand-off between processes; lost on restart |
| Kafka topics `<location>_<point>` | Feedback messages, one partition per camera | Latest only | Short-lived | Feedback controller | Kafka-WebApp | Displays need only current messages, so the topics hold nothing durable |
| `FACIAL-RECOGNITION-DATASET/` | `<person_id>/<pose>.jpg`, 5 or 10 photos each | Read on enrolment | 1 person, 2.2 MB | Owner, DVC | `enrol_person.py` | Versioned by DVC on the dataset store. Vectors are rebuilt from these photos |
| `DISPLAY-FACE-DATASET/` | `<id>/front_face.jpg` | By ID | 1 person | Owner, DVC | Display server | Plain files are enough for lookup by ID |
| `DYNAMIC-FACIAL-RECOGNITION-DATASET/` | Crops and `meta.json` | By person and cluster | Grows | Face collector | Nightly updater | Not in DVC |
| Embeddings pickle | `{"names": [...], "encodings": [...]}` | Whole file | About one vector per image | Enrolment, updater | Upload script | No model or image lineage; unsafe to load from an untrusted source |

Models, thresholds and datasets are pinned together in `mlops/model-manifest.json`, and CI fails on drift (D-012).

Planned, not built: Parquet in place of pickle, one Milvus collection per embedding version behind an alias, and lineage in the manifest. See [features/dataset-versioning.md](features/dataset-versioning.md).
