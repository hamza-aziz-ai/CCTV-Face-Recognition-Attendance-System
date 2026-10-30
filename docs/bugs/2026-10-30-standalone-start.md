# Bug: standalone services would not start on the Windows host

**Symptom:** the start script exited 0, but InsightFace, Milvus and Kafka did not come up.

**Root causes**

1. The old duplicate script under `STANDALONE-SERVICES/` ignored `HOST_PROFILE` and used the A100 MIG layout. The AI gave the owner that command by mistake.
2. `fastrlock` 0.8.4 has no Python 3.8 wheel: `#error Cython requires Python 3.9+`.
3. The MinIO image could no longer be pulled: MinIO withdrew its free images.
4. Stopped containers from older setups held names like `broker`.
5. Shell scripts in the dev checkout still had CRLF, from before `.gitattributes`.
6. Git Bash rewrote the mount target `:/app` to `C:\Program Files\Git\app`: `No module named api_trt.prepare_models`.

**Fix:** PR #16: pin `fastrlock==0.8.3`, `pgsty/minio`, `MSYS_NO_PATHCONV=1` with `pwd -W`, remove the duplicates. 17 old containers removed with the owner's approval; CRLF scripts re-checked out.

**Verification:** both InsightFace containers healthy; `/info` lists `scrfd_10g_gnkps` and `w600k_r50`; Milvus `/healthz` OK.

## Log

- 2026-10-30: first run failed, fixes applied, second run healthy.
