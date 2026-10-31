# Dependencies and secrets

Exact versions live in the requirements files and compose files. This log says why each one is here and who maintains it.

## Services

| Dependency | Why | Maintainer |
|---|---|---|
| PostgreSQL | Attendance and face metadata | PostgreSQL project, official image |
| Milvus | Vector search on the GPU | Zilliz / Milvus project |
| etcd | Milvus metadata | etcd project; version pinned by Milvus |
| `milvusdb/minio` | Milvus object storage, the Milvus-tested build | Published by the Milvus project |
| `pgsty/minio` | Dataset store. MinIO withdrew its free images | Pigsty, a community fork. Lowest trust here |
| Confluent cp-kafka and tools | Feedback messages | Confluent, community edition |
| `cnfldemos/*` | Connect and Flink, from the official compose file; the app does not use them | Confluent demo images |
| InsightFace-REST | Detection and embeddings. Vendored 0.9.5.0, upstream `fb854d8` with local changes (D-031) | SthPhoenix, one maintainer, last commit 2025-06 |
| TensorRT container | GPU inference: `26.07-py3` (TensorRT 11.1, CUDA 13.3), pinned by digest | NVIDIA |
| nginx | Load balancer for InsightFace | nginx project; not pinned yet |

## Python

| Package | Why | Maintainer |
|---|---|---|
| numpy, opencv-python | Frames and images | NumPy, OpenCV projects |
| fastapi, uvicorn, pydantic | HTTP services | Tiangolo, Encode, Pydantic |
| flask, Flask-SocketIO | Display client | Pallets, Miguel Grinberg |
| confluent-kafka | Kafka client | Confluent |
| pymilvus | Milvus client | Milvus project |
| psycopg2-binary | Postgres client | psycopg |
| matplotlib | Tiled frame reports | Matplotlib |
| apscheduler, schedule | ERP push and nightly jobs | Community |
| requests, msgpack, ujson, python-multipart, python-dotenv, typing-extensions | Plumbing | Community |

## Tools

DVC (`uv tool`, this laptop) for datasets; `uvx ruff`, actionlint, shellcheck and gitleaks in CI, or as temporary containers.

## Secrets

Names only, never values.

| Secret | Lives in | Used by |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | `.env` | Postgres and its clients |
| `API_KEY` | `.env` | Reporting API |
| `CAM_USERNAME`, `CAM_PASSWORD` | `.env` | Cameras |
| `DATASET_STORE_USER`, `DATASET_STORE_PASSWORD` | `.env` | Dataset store, DVC |
| DVC credentials | `.dvc/config.local` | DVC |
| `SECRET_KEY` | Random at each start, or the environment | Kafka-WebApp |
| `minioadmin` default login | Milvus compose file, in git | Milvus MinIO. A known gap, see [THREAT.md](THREAT.md) |
| ghcr.io login | Docker Desktop credential store | Watcher |
| GitHub login | `gh` keyring | Watcher |

`.env` exists in the dev checkout and in `C:\deploy\cctv`. Scans: gitleaks runs in CI on every PR.
