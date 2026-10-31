# Architecture

Reads frames from IP cameras, recognizes faces, records attendance and shows the result on displays. The diagram is in the [README](../README.md#architecture). Execution order is in [FLOW.md](FLOW.md), stored data in [DATA.md](DATA.md).

## Modules

| Module               | Code                                         | Owns                                                                              |
|----------------------|----------------------------------------------|-----------------------------------------------------------------------------------|
| Producer-consumer    | `src/main.py`, `src/multicam_stream_*.py`    | Camera threads, frame queue, recognition workers                                  |
| DB controller        | `src/database_server/`                       | Writes recognition results to PostgreSQL                                          |
| Feedback controller  | `src/feedback_server/`                       | Publishes recognition feedback to Kafka                                           |
| Reporting API        | `src/api/`                                   | Reports for people, cameras and locations; pushes records to the ERP every minute |
| Display image server | `src/fetch_face_image_server/`               | Turns recognised IDs into portraits for displays                                  |
| Face collector       | `src/dynamic_face_data_collector/`           | Stores face crops and metadata                                                    |
| Nightly updater      | `src/automatic-vector-db-updation/`          | Moves new crops into the Milvus staging collection                                |
| Kafka-WebApp         | submodule, own repository                    | Display client, on this host and on Raspberry Pis                                 |
| InsightFace-REST     | `STANDALONE-SERVICES/InsightFace-REST`       | Face detection and embeddings on the GPU                                          |
| Milvus               | `STANDALONE-SERVICES/Milvus-Vector-Database` | Vector search                                                                     |
| Kafka                | `STANDALONE-SERVICES/Confluent-Kafka`        | Feedback messages                                                                 |
| Dataset store        | `STANDALONE-SERVICES/Dataset-Store`          | DVC remote for the face datasets                                                  |
| Deployment watcher   | `deploy/watch.py`                            | Deploys new releases to this host, rolls back on failure                          |

## Trust boundaries

Outside input enters at these points. Details and gaps are in [THREAT.md](THREAT.md).

- Camera streams (RTSP or HTTP), read by the camera threads.
- The reporting API on port 9090, the only endpoint with a key.
- Every other published port: 8000, 20001, 20012, 20013, 9095, the Postgres port, 6385, 19000, 19001, 19530, 9000, 9001, 9010, 9011, 9092. None of these has network-level protection, and most have no login.
- The ERP, which receives records and whose responses the API reads.
- GitHub Releases and ghcr.io, which the watcher trusts for what to deploy.

## Hosts

This laptop (RTX 4050, 6 GB, Docker Desktop) is both the dev and the deployment host. The repo's defaults describe the original A100 MIG host; `STANDALONE-SERVICES/hosts/laptop-rtx4050.env` overrides them here (D-015).
