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
- `.github/workflows/release.yml` (branch `ci/release`, stacked on #3): automerge starts it after merging; it bumps from the merged Conventional Commit titles, re-runs `ci` on the exact commit, then tags and publishes a Release with the model manifest attached (D-014).
- GPU host profile `STANDALONE-SERVICES/hosts/laptop-rtx4050.env` (branch `ops/laptop-gpu-profile`, stacked on #4): GPU 0 for everything, batches det 8 / rec 16. It is active once `HOST_PROFILE=laptop-rtx4050` is in `.env` (D-015).
- `deploy/watch.py` with `deploy/test_watch.py` (branch `ops/deploy-watcher`, stacked on #5): a pull-based deployment watcher with rollback; images are tagged per release via `IMAGE_TAG`. Setup is in the README under CI/CD (D-016). It is not installed yet: that needs PRs #1–#6 merged and a first release.
- PRs #1–#6 merged. #2–#6 were recreated as #7–#11 after a stacked base branch was deleted: #2 closed, and an accidental push marked #3–#6 merged into a side branch. Auto-merge took #9–#11 and released v0.1.0 and v0.2.0, with no images.
- Release images: `release.yml` pushes the 7 app images to `ghcr.io/hamza-aziz-ai/cctv-face-recognition-<service>:<tag>` before tagging; the watcher pulls them instead of building (D-017).
- Restart policies (`unless-stopped`) on all standalone and main-stack containers; InsightFace-REST upstream recorded in the manifest; headless (no sign-in) plan written in D-018, not built.
- Kafka-WebApp: the owner chose to absorb it into this repo (not a submodule). It must run both on this host and on Raspberry Pis (amd64 and arm64 images). Not started.
- Standalone services running on this host (2026-10-30) via the root `./start_standalone_services.sh` with `HOST_PROFILE=laptop-rtx4050`: InsightFace-REST (2 workers on GPU 0 behind nginx :6385, TRT engines built), Milvus (MinIO now `pgsty/minio`; MinIO withdrew its free images), Kafka. Fixes: `fastrlock==0.8.3` pin, Git Bash mount paths, duplicate scripts under `STANDALONE-SERVICES/` removed. Dev checkouts made before `.gitattributes` may still hold CRLF `.sh` files: delete and `git checkout --` them.
- Repo settings applied: squash merge only (PR title and body become the commit), automatically delete head branches. Dependabot alerts, Dependabot security updates and the read-only default workflow token were already on.

In progress:
- PR #1 (`ci/docker-packaging`): step 2 commits are local-verified (8 builds and smoke tests pass); waiting for the first `ci` run on GitHub.

Broken or risky:
- This machine is both the dev and the deployment server (from 2026-10-30): Windows 11, Docker Desktop, RTX 4050 Laptop 6 GB. The repo config assumes an A100 host:
  - The MIG slices and A100 batch sizes are handled by the `laptop-rtx4050` host profile (D-015), but the profile's batch sizes have not been tested on the GPU yet.
  - InsightFace TAG `v0.9.0.0` is built by `deploy_trt_multi-gpu.sh` itself; the local `v0.9.5.0` image is unrelated.
  - Milvus `v2.5.1-gpu` in the repo; `v3.0.0` is the local image.
  - Compose `/workspace/...` paths land inside the Docker Desktop VM.
  - No TensorRT engines are built yet. The stack has not been started here.
- `src/main.py` deletes Kafka topics at startup. Pending feedback may be lost on restart (unverified).
- `src/automatic-vector-db-updation/milvus_updater.py` deletes old vectors, swallows insert failures and still marks the rows processed. This loses vectors silently.
- Python 3.11 has only been verified by build, `pip check` and import smoke tests; no live pipeline run yet.
- Existing hosts must rebuild images before the next `up` after merging PR #1. The old `v-beta` images contain no code, and the base compose no longer mounts `./src`.
- Dependabot reports 9 vulnerabilities (5 high, 4 moderate), not yet triaged.
- Stacked PRs and squash merges: deleting a merged base branch closes the PR stacked on it. Retarget dependents to `main` before merging, then merge `main` into each branch.

Next:
- After v0.3.0 (first release with images): `gh auth refresh -s read:packages`, `docker login ghcr.io`, then create the deploy clone `C:\deploy\cctv`, copy `.env` into it, run `watch.py --enroll` and register the scheduled task (README, CI/CD).
- Turn on Docker Desktop "Start Docker Desktop when you sign in" (owner).
- Absorb Kafka-WebApp (GIV-AI/Kafka-WebApp at `4578453`), drop the broken `.gitmodules` entry, and add it to CI, releases and the watcher.
- Pull the datasets with DVC; none are present on this machine.
- Actions budget (account Billing page, manual). Allow Actions to create PRs only when `release.yml` lands.
- Map the producer-consumer runtime files to explicit mounts, replacing its whole-repo `.` mount.
- Fill the 4 null manifest values from the GPU host (commands are in the manifest's `unverified` block).

Do not touch:
- `STANDALONE-SERVICES/` upstream services (InsightFace-REST, Milvus, Kafka).
- The `Kafka-WebApp` submodule (belongs to another account).
- Production hosts: no deployment automation until the phase-two criteria in the plan are met. Never run a self-hosted Actions runner on this machine: it is also the dev box.
