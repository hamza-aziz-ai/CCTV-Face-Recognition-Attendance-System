# Rollback

## App stack

Automatic: if a deployment fails, the API smoke test fails, or a service is restarting 90 seconds later, `deploy/watch.py` starts the previous release, records the failed tag and shows a Windows message. It never retries that tag on its own. The current and previous release images stay on disk.

By hand, to leave a release that passed its checks but behaves badly:

1. Revert its squash commit in a PR. Green CI merges it and a new release deploys.
2. To retry a failed tag: `python deploy\watch.py --enroll` in `C:\deploy\cctv`.

To stop automatic deploys: `schtasks /Change /TN "CCTV deploy watcher" /DISABLE`.

## Data changes

| Change                      | How to undo                                                                                                                                                                                                                                                                                                                                    |
|-----------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| PostgreSQL 12 to 18 (D-020) | Not possible any more: the 12 data was deleted on 2026-10-31, after the client names were removed.                                                                                                                                                                                                                                             |
| Milvus 2.5 to 3.0 (D-022)   | Not possible any more: the 2.5.1 test data was deleted on 2026-10-31.                                                                                                                                                                                                                                                                          |
| Face vectors (D-030)        | `python3 src/util/face_vectors.py list`, then `use <n>` to serve an earlier version; the app follows without a restart. For a version no longer in Milvus, check out that dataset version (`git checkout <commit> FACIAL-RECOGNITION-DATASET.dvc && dvc checkout`) and `publish`. Before the migration, `use 0` returns to the old collection. |
| Kafka                       | Topics live in the `kafka-data` volume (D-028). To start empty, stop the Kafka stack and remove `confluent-kafka_kafka-data`; each service recreates its own topics.                                                                                                                                                                           |
| Dataset store               | `stop_standalone_services.sh` keeps `DATASET_STORE_DIR`. There is no second copy of it yet.                                                                                                                                                                                                                                                    |

## Standalone services

These are not managed by the watcher. Revert the compose change, then run `./start_standalone_services.sh`.

InsightFace 0.9.0 to 0.9.5 (D-031): revert the PR, so `TAG` is `v0.9.0.0` and `src/api_trt` is back, then run `./start_standalone_services.sh`. The old TensorRT 8.5 engines are kept, because 0.9.5 names its engines with the TensorRT version.

## After any rollback

Run the live checks in [TEST-CHECKLIST.md](TEST-CHECKLIST.md), and note it in [HANDOVER.md](HANDOVER.md).

## Limits

A rollback does not undo writes to Postgres or Milvus. There is no feature flag for any change, and no automated database backup.
