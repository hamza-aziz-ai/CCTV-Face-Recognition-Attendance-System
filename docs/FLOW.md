# Flow

## Startup

`src/main.py`, `if __name__ == "__main__"`:

1. `set_start_method("fork")`: the workers inherit live Milvus collections (D-023).
2. `create_connection()` and `create_collection()` for the primary and staging collections, then `load_with_retry()`.
3. `delete_kafka_topics()`, then `create_kafka_topics()`, then a 30 s wait. Topics are recreated on every start.
4. Starts the `producer_main` process, then runs `consumer_main` in the main process.

## Recognition path

```text
camera
  -> multicam_stream_producer.py: place_frame_in_buffer()   ROI crop or resize to 640x360, skip dark frames
  -> MULTIPROCESS_SHARED_BUFFER (multiprocessing.Queue)     in memory, lost on restart
  -> multicam_stream_consumer.py: face_recognition()        2 processes, batches of 32 frames
  -> nginx :6385 -> InsightFace-REST /extract               detection and 512-d embeddings
  -> src/milvus_server.py: search_embedding()               top 5 from primary and staging
  -> accept: primary cosine similarity >= 0.5, or a staging match when STAGING = True
  -> POST /ingest   -> database_server -> PostgreSQL
  -> TCP JSON :20012 -> feedback_server -> Kafka            strict primary matches only
  -> POST /faces    -> dynamic_face_data_collector          strict primary matches only
```

## Display path

```text
Kafka topic <location>_<point>
  -> Kafka-WebApp app.py: _consume_messages()               waits until the health-check ports answer
  -> POST /post_images -> fetch_face_image_server           returns portraits
  -> Socket.IO -> browser on the display
```

## Other paths

- Reports: client -> `src/api/app.py` -> PostgreSQL.
- ERP: `src/api/app.py` scheduler, every minute -> ERP.
- Nightly, 01:00: `milvus_updater.py` -> PostgreSQL for new crops -> InsightFace-REST for embeddings -> Milvus staging, and the embeddings pickle.
- Release: PR -> `ci` -> `automerge` -> `release` -> ghcr.io images, deploy bundle, tag, GitHub Release, bundle `:stable` -> `watch.py` every 10 minutes pulls `:stable` and stages the bundle -> `compose up --pull missing --wait` from the bundle with `site\` -> smoke test on `:9090/docs`.
