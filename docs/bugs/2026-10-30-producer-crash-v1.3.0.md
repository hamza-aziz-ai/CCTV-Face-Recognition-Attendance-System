# Bug: producer-consumer crash-looped on v1.3.0, and the deploy still passed

**Symptom:** `producer-consumer` was `Restarting (1)` after v1.3.0 deployed: `RuntimeError: context has already been set` at `src/main.py` line 55. The watcher logged `Deployed v1.3.0`.

**Repro:** start `src/main.py` on Python 3.14.

**Root causes**

1. PR #24 called `set_start_method("fork")` in `main.py`, but `multiprocessing_shared_buffer.py` creates a `Queue` at import, which fixes the start method first. The checks for that PR covered names, imports and `pip check`, and CI never starts `main.py`.
2. The watcher only smoke-tested the API. A service with a restart policy and no healthcheck counts as started for `up --wait`.

**Fix:** set `fork` in `multiprocessing_shared_buffer.py`, above the queue. The watcher now fails a deploy if any service is restarting or exited 90 seconds after the smoke test.

**Verification:** patched `main.py` run for real in the v1.3.0 image against the live services: no start-method error, and it reached Milvus. `deploy/test_watch.py` covers the crash-loop check.

**Found along the way:** with no enrolled faces, `load_with_retry` repeats `index not found` forever. So this process has not got past Milvus in any release on this host.

## Log

- 2026-10-30 23:16: v1.3.0 deployed with the crash loop; no real cameras, so nobody was affected.
- 2026-10-30: fix tested and committed.
