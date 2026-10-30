# Bug: ghcr.io denied image pushes

**Symptom:** the v0.3.0 release run failed: `error from registry: denied`, for 7 of 7 images, then 4 of 7 on a re-run, a different set each time.

**Repro:** `docker compose push` of 7 new packages at once from `release.yml`.

**Tried:** re-running the failed job (no fix, ruling out a race on the first creation only); comparing with Medical-ChatBot's workflow (same login).

**Root cause:** inferred, not confirmed by GitHub: parallel pushes of shared base layers into new packages.

**Fix:** PR #13: `docker compose --parallel 1 ... push`.

**Verification:** release run 41051402964: `images success`, `publish success`; all 7 packages tagged `v0.3.0`.

## Log

- 2026-10-30: 7 of 7 denied, then 4 of 7 denied, then fixed.
