# Rollback

## App stack

Automatic: if a deploy fails, the API smoke test fails, or a service is restarting 90 seconds later, `deploy/watch.py` starts the previous release, records the failed tag and shows a Windows message. It never retries that tag on its own. The current and previous release images stay on disk.

By hand, to leave a release that passed its checks but behaves badly:

1. Revert its squash commit in a PR. Green CI merges it and a new release deploys.
2. To retry a failed tag: `python deploy\watch.py --enroll` in `C:\deploy\cctv`.

To stop automatic deploys: `schtasks /Change /TN "CCTV deploy watcher" /DISABLE`.

## Data changes

| Change | How to undo |
|---|---|
| PostgreSQL 12 to 18 (D-020) | Folder `/workspace/database/postgresql/cctv-face-recognition` in the Docker VM keeps the 12 data. Deploying a release before v1.0.0 uses it again. |
| Milvus 2.5 to 3.0 (D-022) | Restore `/usr/local/database/milvus-2.5.1-backup` to `/usr/local/database/milvus` in the Docker VM, and revert the compose change. |
| Kafka | Nothing to restore: topics are recreated at start. |
| Dataset store | `stop_standalone_services.sh` keeps `DATASET_STORE_DIR`. There is no second copy of it yet. |

## Standalone services

These are not managed by the watcher. Revert the compose change, then run `./start_standalone_services.sh`.

## After any rollback

Run the live checks in [TEST-CHECKLIST.md](TEST-CHECKLIST.md), and note it in [HANDOVER.md](HANDOVER.md).

## Limits

A rollback does not undo writes to Postgres or Milvus. There is no feature flag for any change, and no automated database backup.
