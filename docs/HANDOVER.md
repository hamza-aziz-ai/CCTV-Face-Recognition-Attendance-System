# HANDOVER

Read first: docs/DECISIONS.md. Newest entry on top.

## Latest session: 2026-10-30 (model: Claude Opus 5.5, council with Codex gpt-6.1-sol)

Done:
- Agreed the CI/CD and MLOps plan with Codex. The order is: packaging fixes → CI → DockerHub and release-please → DVC and model manifest → deployment design.
- Step 2 (branch `ci/docker-packaging`):
  - Images move to Python 3.11 on bookworm and bake in `src/`.
  - `.dockerignore` rewritten.
  - Healthchecks fixed.
  - `master.env` untracked.
  - `.gitattributes` forces LF on `.sh`.
- Step 3 (same branch): `.github/workflows/ci.yml` runs lint, gitleaks, compose config, 8 image builds and smoke tests, plus the aggregate `ci` check. Two dead `del` blocks removed (D-007).
- Compose split: `docker-compose-main.yml` has no builds or `./src` mounts (code comes from the image). `docker-compose.dev.yml` restores both. `build-docker-images.sh` removed; the README builds via the dev override (D-010).
- `.github/dependabot.yml`: weekly grouped updates for github-actions and the Docker base digest (D-011).
- `mlops/model-manifest.json` and `mlops/check_manifest.py` (branch `mlops/model-manifest`, stacked on PR #1). CI fails on drift; `--release` fails while 4 host-only values are null (D-012).
- `.github/workflows/automerge.yml` (branch `ci/automerge`, stacked on #2): squash-merges PRs into main when `ci` and every other check passed on the exact head commit; it runs only from main's copy (D-013). It only takes effect once merged to main, so #1–#3 themselves are merged by hand.
- Repo settings applied: squash merge only (PR title and body become the commit), automatically delete head branches. Dependabot alerts, Dependabot security updates and the read-only default workflow token were already on.

In progress:
- PR #1 (`ci/docker-packaging`): step 2 commits are local-verified (8 builds and smoke tests pass); waiting for the first `ci` run on GitHub.

Broken or risky:
- This machine is both the dev and the deployment server (from 2026-10-30): Windows 11, Docker Desktop, RTX 4050 Laptop 6 GB. The repo config assumes an A100 host:
  - `standalone-services.env` pins the InsightFace and liveness GPUs to MIG slices `7:0`..`7:3`, which this GPU cannot provide.
  - Detection and recognition batch sizes are 64 and 128, sized for an A100.
  - InsightFace TAG `v0.9.0.0` in the repo; `v0.9.5.0` is the local image.
  - Milvus `v2.5.1-gpu` in the repo; `v3.0.0` is the local image.
  - Compose `/workspace/...` paths land inside the Docker Desktop VM.
  - No TensorRT engines are built yet. The stack has not been started here.
- `src/main.py` deletes Kafka topics at startup. Pending feedback may be lost on restart (unverified).
- `src/automatic-vector-db-updation/milvus_updater.py` deletes old vectors, swallows insert failures and still marks the rows processed. This loses vectors silently.
- Python 3.11 has only been verified by build, `pip check` and import smoke tests; no live pipeline run yet.
- Existing hosts must rebuild images before the next `up` after merging PR #1. The old `v-beta` images contain no code, and the base compose no longer mounts `./src`.
- Dependabot reports 7 vulnerabilities (4 high, 3 moderate), not yet triaged.

Next:
- `release.yml`: version bump from the merged PR's conventional title, then a tag and Release (chained via `workflow_run` from automerge; no PAT).
- Deployment watcher on this machine: Task Scheduler runs a poller of the latest release, which deploys from a separate clone, health-checks, and rolls back to the last good tag on failure.
- Actions budget (account Billing page, manual). Allow Actions to create PRs only when `release.yml` lands.
- Map the producer-consumer runtime files to explicit mounts, replacing its whole-repo `.` mount.
- Fill the 4 null manifest values from the GPU host (commands are in the manifest's `unverified` block).
- DockerHub repo and secrets, then `release.yml` with release-please, gated on `check_manifest.py --release`.

Do not touch:
- `STANDALONE-SERVICES/` upstream services (InsightFace-REST, Milvus, Kafka).
- The `Kafka-WebApp` submodule (belongs to another account).
- Production hosts: no deployment automation until the phase-two criteria in the plan are met. Never run a self-hosted Actions runner on this machine: it is also the dev box.
