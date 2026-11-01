# Bug: Postgres and Milvus data were lost when the laptop restarted

**Symptom:** on 2026-11-01 the host's old watcher logged `Deploy of v2.3.0 failed: not stable after 90s: automate-milvus-update, mfr-cctv-producer-consumer`, then `ROLLBACK TO v2.1.0 FAILED` with the same reason. `milvus-standalone` had restarted 164 times, with `mkdir /var/lib/milvus/data: permission denied`. PostgreSQL ran but held 0 rows, and its data folder was dated that morning's boot.

**Root cause:** Postgres (`/workspace/database/...`) and Milvus, its etcd and its MinIO (`DOCKER_VOLUME_DIRECTORY=/usr/local/database/milvus`) used bind mounts to Linux paths. On Docker Desktop those paths live in the VM's filesystem, which does not survive a restart. Shutting the laptop down emptied them. Milvus then failed because its folder came back owned by root and `milvus-volume-init`, a one-shot, did not run again. HANDOVER already noted that `/workspace/...` lands inside the VM; the consequence was never tested, because the laptop had not been restarted since.

**Lost:** the recognition records in `CCTV_Camera_Surveillance`, the collected-crop records in `Face_Recognition_Database`, and the Milvus staging vectors. All were test data. **Not lost:** the face dataset (the DVC store is on `C:\data\dataset-store`, a Windows path), Kafka topics (already a named volume, D-028), and the site configuration.

**Fix:** named Docker volumes for PostgreSQL (`cctv-postgres-data`) and Milvus (`milvus-data`, `milvus-etcd`, `milvus-minio`) (D-038). Primary vectors were rebuilt from the dataset with `face_vectors.py publish`: 10 rows, serving `_v2`.

**Lesson:** a restart is a test. Anything stateful on Docker Desktop must be on a named volume or a Windows path, and a stateful service's persistence must be proved by restarting it. The Kafka topics surviving this same restart show what a named volume does.
