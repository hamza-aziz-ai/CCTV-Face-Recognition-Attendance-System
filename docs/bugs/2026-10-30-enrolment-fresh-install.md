# Bug: enrolment script and fresh installs blocked by Milvus setup

**Symptoms**

1. `src/util/insightface_embeddings.py` could not run on this host: it used `localhost:18081`, then ended with `should create connection first`.
2. On a fresh install, `producer-consumer` repeated `index not found` forever, and never started recognition.

**Repro:** run the enrolment functions on this host; start `main.py` with empty Milvus collections.

**Root causes**

1. The script hard-coded the InsightFace address, and ended with an upload to `localhost` into a `FACE_EMBEDDINGS` collection that nothing reads.
2. Only `insert_data()` created an index, and Milvus cannot load a collection without one. An empty collection could never load.

**Fix:** the script takes its address from `parameters.py` and only writes the pickle; `upload_embeddings.py` does the upload. `create_collection()` now ensures an index on new and existing collections, and `insert_data()` no longer creates one. Index type and search settings are unchanged.

**Verification (v1.3.0 image, live services):**

- New empty collection loads, `GPU_IVF_FLAT`. Existing staging collection with no index loads.
- Enrolment through the repaired script: 174 vectors, then 191 unseen LFW photos: 180 correct, 0 wrong, 11 below threshold, same as before the change.
- `main.py` passes Milvus, recreates its Kafka topics, starts the producer and tries the cameras.

## Log

- 2026-10-30: found during the LFW test, fixed and verified.
