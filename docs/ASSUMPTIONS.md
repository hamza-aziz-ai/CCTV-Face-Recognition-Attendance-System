# Assumptions and open questions

Mark each item verified, unverified or wrong. Clear or consciously accept the unverified ones before real people depend on the system.

| Assumption | Status | Note |
|---|---|---|
| Parallel pushes caused the ghcr.io `denied` errors | Unverified | Pushing one at a time fixed it; GitHub never confirmed the cause |
| FP16 and batch sizes 8/16 fit real load on 6 GB | Unverified | Guesses (D-015) |
| NumPy 2 and OpenCV 5 recognise correctly | Verified, in a small test | 191 unseen LFW photos of 30 people: 180 correct, 0 wrong, 11 below threshold. Not compared with the old versions, and not CCTV footage |
| pymilvus 3.0 and Python 3.14 work with `fork` | Unverified | `main.py` runs, loads Milvus and starts the producer; no frame has reached a worker, because no camera is connected |
| Kafka-WebApp arm64 image runs on a real Raspberry Pi | Unverified | Passed under emulation in CI |
| Kafka-WebApp page updates in a browser | Unverified | Message reached the image server (200); the page itself was not watched |
| `camera_configuration.json` here is a copy of the example | Accepted | Owner's choice; no real cameras yet |
| Accuracy metrics from the original deployment hold on this stack | Unverified | They were measured on other versions |
| The app works with an empty Milvus | Verified | Fixed in #31: collections get an index when created |
| PostgreSQL 18 works with the app | Verified | Deployed v1.0.0, containers healthy |
| Kafka 8.4 works with confluent-kafka 2.16 | Verified | Produce and consume roundtrip |
| Milvus 3.0.5 GPU index works | Verified | 512-d `GPU_IVF_FLAT` search returned the query vector |

## Open questions

- Should the Raspberry Pis pull a public image, or log in to ghcr.io?
- Should the release gate fail while manifest values are still null?
- Should the app move off pickle before or after the datasets are migrated?
- InsightFace 0.9.5 on TensorRT 11 was compared with 0.9.0 on LFW only, not on CCTV footage (D-031).
- Retention period for frames and face data?
- How to serve several clients: one central service or dedicated deployments? The code currently serves one site.
