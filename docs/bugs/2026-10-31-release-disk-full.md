# Bug: release runs failed in the images job

**Symptom:** the v2.0.0 release run failed in `images` with no readable log. Two runs after the Python 3.14 change failed the same way. The job's annotation read `No space left on device`.

**Root cause:** the job builds all 7 images on one GitHub runner, and the Python 3.14 images are larger, so the disk filled. Some runs fit and some did not.

**Fix:** the job deletes preinstalled toolchains it does not use before building, and prints `df -h /`.

**Related:** while this release was pending, v1.4.0 failed and its rollback to v1.3.1 failed too, because `INSTITUTE` had been removed from `master.env` before v2.0.0 existed. Host config must only change after the release that needs the change is deployed.

## Log

- 2026-10-31 00:45 IST: v1.4.0 deploy and rollback failed, stack down.
- 2026-10-31 00:49 IST: v2.0.0 release failed on disk space.
