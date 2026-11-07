# HANDOVER

Read first: docs/ARCHITECTURE.md, docs/CONSTRAINTS.md, docs/DECISIONS.md. Newest entry on top.

## Session summary: 2026-11-01 (model: Claude Opus 5.5)

Done: every open PR merged (#53 to #81) and v2.6.3 deployed by the watcher. This host runs from the bundle layout in `C:\deploy\host`, with no git clone. D-037 cutover done: the owner's stack uses its own logins, Kafka and Milvus require them, and the unused Kafka add-ons are gone. PostgreSQL and Milvus are on named volumes, and a full laptop restart was tested after the cutover. Images are tagged and digest rows cleared on every watcher run.

End-to-end test passed on a real RTSP camera: name and portrait on the display, record saved, API returned it. The ERP is untested, because its address is a placeholder. That test found records had never saved on a fresh table (#79), duplicates from parallel batches (#80), and three smaller bugs (#81).

State: Claude Code Review is paused, at the owner's choice (`gh workflow enable claude-code-review.yml`). Small docs, Markdown and submodule chores go straight to `main` with `[skip ci]`, subject `docs:` or `chore:`. `kafka-ui` runs with `--profile ui`, on its read-only login. Rollback compose files are in `C:\deploy\host
ollback-compose`, and the backup in `C:\deployackup`.

Late update: v2.8.0 is deployed and D-036 step 4 is done (D-039, D-040). Accounts, sessions and machine tokens are in the API, and `?api_key=` is gone. `cctv-proxy` serves https://owner.localhost on 443, and the API, display and portrait ports are on 127.0.0.1 only. It was started by hand from the release folder with `PROXY_DIR` set, and `start_standalone_services.sh` starts it from now on. The watcher restarts healthy containers whose published ports die after a reboot (#82). The owner must trust the proxy's CA once; the commands are in the README. Nothing starts after a reboot until someone signs in to Windows. Raspberry Pi displays would need a route for portraits.

Agreed order (owner, 2026-11-01). This replaces the list below.

1. Done: accuracy check on a real camera in good light, on both the laptop and the Jetson (owner, 07 Nov 2026). Laptop, 02 Nov 2026, brightness 71 to 155: 8 records, 0.603 to 0.774, mean 0.715 (was 0.549 and 0.559 in poor light on 01 Nov). Jetson edge, 02 Nov 2026: 39 records in 80 s, 0.482 to 0.784, mean 0.709; 06 Nov 2026 edge layout: 0.725. All one enrolled person (the owner). The 02 Nov runs predate the RGB fix (#112, 06 Nov); the 06 Nov score and the LFW measurement of the 0.5 threshold (docs/ASSUMPTIONS.md) follow it. CCTV footage with labelled people is still unmeasured.
2. D-036 step 5: tiers (D-041) and snapshot, restore and remove (D-042) are done, and the live rehearsal with a temporary client proved `restore` rebuilds Milvus with the real `face_vectors.py publish` (D-042). `recovery.py` is installed on the host by hand. The ID `rehearsal` is spent on this broker. On 2026-11-02 `cctv-proxy` and `milvus-standalone` were recreated from the v2.9.2 bundle, so no container mounts the old v2.6.2 or v2.8.0 folders; the proxy answered HTTPS after the recreate and after a restart, and Milvus kept the owner's versions. `milvus-etcd` and `milvus-minio` were left running, as their settings did not change; their labels still name a deleted worktree, `C:\wt23`, and they mount only named volumes.
3. Live view (8b).
4. Enrolment API (8c), then the Android app (8d).
5. Deletion, isolation and recovery tests (8e).
6. Compile the app code with Nuitka: app images still hold readable Python.
7. Signed setup codes, required before the first outside client (Face-Dataset-Collector D-014).
8. Later: ERP test with a real address, PTZ merge, DeepStream tier, Jetson arm64 plan. The Orin Nano has no NVENC, so annotated live view draws boxes in the viewer.

Owner, before any real people are enrolled: sign off the notice, legal basis, consent per re-enrolment and ML Kit disclosure. Also the InsightFace licence email and Dependabot triage. Off-host backups do not exist yet.

## Session summary: 2026-10-31 (model: Claude Opus 5.5, councils with Codex GPT-6.1 Sol)

Context: this project is a rehearsal of real-world deployment, not a sold product. Durations and incidents go into docs/TIMELINES.md so later promises can be kept.

Done: InsightFace-REST 0.9.5 on TensorRT 11, built by CI and running as one container (D-031, D-032); generic GPU defaults instead of the A100 MIG layout; face vectors versioned with the dataset and Milvus served through an alias (D-030, migrated); the display fixed (Kafka-WebApp v0.1.2); Kafka topics kept on a volume (D-028); merge and release self-recovery (D-029); deployment hosts get images and a source-free bundle instead of the repository (D-033, PR #52); former client names removed from every local file, log and config (they remain in git history, left as is); Docker on this host logged in to ghcr.io with a read:packages-only token.

Blocked until 2026-11-01 00:00 UTC (05:30 IST): the month's GitHub Actions minutes are used up, so CI, merges and releases do not run.

Agreed order (owner, 2026-10-31). This replaces the older "Next" lists below.

1. Merge #55 (skip image builds on docs-only PRs).
2. Re-run the failed v2.2.0 release (issue #54): publishes the first bundle and `:stable`.
3. #53 registry watcher: `watch.py --check` against the real `:stable`, take out of draft, release.
4. Let #56 (standalone scripts from a bundle), #57 (TIMELINES.md), this PR and Kafka-WebApp #4 merge.
5. Switch this host to the bundle and `site\` layout and retire the deploy clone (D-033 step 3; planned short outage).
6. Repair the ROI provisioning service (owner: repair, not delete). It imports names that no longer exist (`IP_CAMS`, `create_mask`, `roi_coordinates`) and rewrites `src/parameters.py` at runtime; it is not deployed today.
7. Real camera test of the whole path (owner).
8. Multi-tenant design: client-dedicated and multi-client central deployments from one codebase, including where each client's data lives and staff login (council, decision record). Pull tokens only gate which images a dedicated host can download; central tiers need server-side entitlements.
   - 8b. Standard live view: camera video passed through a media server (e.g. MediaMTX) beside a per-camera "recent events" panel; no overlays.
   - 8c. Enrolment API on synthetic data: staff login, client taken from the login, server-side photo checks (real head pose and blur), jobs in Postgres, Milvus publish only after validation.
   - 8d. Android app `hamza-aziz-ai/Face-Dataset-Collector`: login, consent record, guided 5 or 10-pose auto-capture, review and retake, upload to 8c. Its capture screens can start now against a mock.
   - 8e. Person deletion (photos, vectors, camera crops, old Milvus versions, stored object versions, backups, with a deletion record), plus client isolation and recovery tests.
9. Step 4: compile the app code (Nuitka module mode, Cython fallback, `-rt` packages; plan agreed with Codex). Dedicated tier only.
10. Merge the PTZ project in as a second app (Python 3.14, CI, no secrets in images first).
11. DeepStream as an optional paid recognition image, including the live annotated stream. It starts with a capacity spike: timestamped clips, then 1 to N streams, measuring p95 latency, frame rate, drops, GPU memory, encoder sessions and viewer fan-out. Risks: hardware decoding under WSL2 on RTX 40-series, and consumer GPUs capped at 8 encoder sessions.
12. Jetson Orin edge node. The Orin Nano has no hardware video encoder.

Any time: draft the InsightFace model licence request (owner sends); triage Dependabot alerts; delete `insightface-rest:v0.9.0.0` after a few days of real use; budget Actions minutes for the large builds in items 9 to 12.

Stale in the older entries below: `src/main.py` no longer deletes Kafka topics (#43); the producer no longer mounts the whole checkout (#52); `HOST_PROFILE=laptop-rtx4050` and its profile are gone (#51).

## Session summary: 2026-10-30, late (model: Claude Opus 5.5)

Done: CI/CD end to end; the watcher deploys releases to this host; PostgreSQL 18.6, Kafka 8.4, Milvus 3.0.5, Python 3.14; Kafka-WebApp as a submodule with its own CI and releases; the guide's docs written.
Left: enrol real people with consent; a real camera test; InsightFace 0.9.5 (on hold, see docs/features/); vector versioning (docs/features/dataset-versioning.md); Dependabot alerts.
Risks: no real camera has gone through the system since the upgrades, and only one person is enrolled; most internal services have no login (docs/THREAT.md); the Raspberry Pis cannot pull the private `kafka-webapp` package yet.

## Latest session: 2026-10-30 (model: Claude Opus 5.5, council with Codex GPT-6.1 Sol)

Done:
- Agreed the CI/CD and MLOps plan with Codex. The order is: packaging fixes → CI → DockerHub and release-please → DVC and model manifest → deployment design.
- Step 2 (branch `ci/docker-packaging`):
  - Images move to Python 3.11 on bookworm and bake in `src/`.
  - `.dockerignore` rewritten.
  - Health checks fixed.
  - `master.env` untracked.
  - `.gitattributes` forces LF on `.sh`.
- Step 3 (same branch): `.github/workflows/ci.yml` runs lint, gitleaks, compose config, 8 image builds and smoke tests, plus the aggregate `ci` check. Two dead `del` blocks removed (D-007).
- Compose split: `docker-compose-main.yml` has no builds or `./src` mounts (code comes from the image). `docker-compose.dev.yml` restores both. `build-docker-images.sh` removed; the README builds via the dev override (D-010).
- `.github/dependabot.yml`: weekly grouped updates for GitHub Actions and the Docker base digest (D-011).
- `mlops/model-manifest.json` and `mlops/check_manifest.py` (branch `mlops/model-manifest`, stacked on PR #1). CI fails on drift; `--release` fails while 4 host-only values are null (D-012).
- `.github/workflows/automerge.yml` (branch `ci/automerge`, stacked on #2): squash-merges PRs into main when `ci` and every other check passed on the exact head commit; it runs only from main's copy (D-013). It only takes effect once merged to main, so #1–#3 themselves are merged by hand.
- `.github/workflows/release.yml` (branch `ci/release`, stacked on #3): automerge starts it after merging; it bumps from the merged Conventional Commit titles, re-runs `ci` on the exact commit, then tags and publishes a Release with the model manifest attached (D-014).
- GPU host profile `STANDALONE-SERVICES/hosts/laptop-rtx4050.env` (branch `ops/laptop-gpu-profile`, stacked on #4): GPU 0 for everything, batches det 8 / rec 16. It is active once `HOST_PROFILE=laptop-rtx4050` is in `.env` (D-015).
- `deploy/watch.py` with `deploy/test_watch.py` (branch `ops/deploy-watcher`, stacked on #5): a pull-based deployment watcher with rollback; images are tagged per release via `IMAGE_TAG`. Setup is in the README under CI/CD (D-016). It is not installed yet: that needs PRs #1–#6 merged and a first release.
- PRs #1–#6 merged. #2–#6 were recreated as #7–#11 after a stacked base branch was deleted: #2 closed, and an accidental push marked #3–#6 merged into a side branch. Auto-merge took #9–#11 and released v0.1.0 and v0.2.0, with no images.
- Release images: `release.yml` pushes the 7 app images to `ghcr.io/hamza-aziz-ai/cctv-face-recognition-<service>:<tag>` before tagging; the watcher pulls them instead of building (D-017).
- Restart policies (`unless-stopped`) on all standalone and main-stack containers; InsightFace-REST upstream recorded in the manifest; headless (no sign-in) plan written in D-018, not built.
- Kafka-WebApp is a submodule pointing at `hamza-aziz-ai/Kafka-WebApp` (D-024). It must run both on this host and on Raspberry Pis (amd64 and arm64 images). Its Dockerfile, CI and releases live in that repository.
- Standalone services running on this host (2026-10-30) via the root `./start_standalone_services.sh` with `HOST_PROFILE=laptop-rtx4050`: InsightFace-REST (2 workers on GPU 0 behind nginx :6385, TRT engines built), Milvus (MinIO now `pgsty/minio`; MinIO withdrew its free images), Kafka. Fixes: `fastrlock==0.8.3` pin, Git Bash mount paths, duplicate scripts under `STANDALONE-SERVICES/` removed. Dev checkouts made before `.gitattributes` may still hold CRLF `.sh` files: delete and `git checkout --` them.
- DVC remote: dedicated MinIO dataset store (`STANDALONE-SERVICES/Dataset-Store`, port 9010, bucket `dvc`), default remote `minio` in a now-tracked `.dvc/config` (D-019). Verified with a throwaway instance: `dvc push` 2 files, local copy deleted, `dvc pull` restored them. Datasets still need migrating from the Google Drive remote.
- Repo settings applied: squash merge only (PR title and body become the commit), automatically delete head branches. Dependabot alerts, Dependabot security updates and the read-only default workflow token were already on.

In progress:
- InsightFace 0.9.5 on TensorRT 11 is ready to switch (D-031): run `./start_standalone_services.sh` after the PR merges.

Broken or risky:
- This machine is both the dev and the deployment server (from 2026-10-30): Windows 11, Docker Desktop, RTX 4050 Laptop 6 GB. The repo defaults are generic and fit it: every GPU service on GPU 0, one InsightFace container with batch sizes 8 and 16 (D-032). Speed and memory under real camera load are not measured.
  - InsightFace TAG `v0.9.5.0` is built by `deploy_trt_multi-gpu.sh` itself. Keep the old `v0.9.0.0` image until the switch is proven, for a rollback.
  - Milvus `v2.5.1-gpu` in the repo; `v3.0.0` is the local image.
  - Compose paths like `/workspace/...` land inside the Docker Desktop VM and are emptied by a restart, so stateful services use named volumes (D-038).
  - No TensorRT engines are built yet. The stack has not been started here.
- `src/main.py` deletes Kafka topics at startup. Pending feedback may be lost on restart (unverified).
- `src/automatic-vector-db-updation/milvus_updater.py` deletes old vectors, swallows insert failures and still marks the rows processed. This loses vectors silently.
- Python 3.11 has only been verified by build, `pip check` and import smoke tests; no live pipeline run yet.
- Existing hosts must rebuild images before the next `up` after merging PR #1. The old `v-beta` images contain no code, and the base compose no longer mounts `./src`.
- Dependabot reports 9 vulnerabilities (5 high, 4 moderate), not yet triaged.
- Stacked PRs and squash merges: deleting a merged base branch closes the PR stacked on it. Retarget dependents to `main` before merging, then merge `main` into each branch.

Next:
- After v0.3.0 (first release with images): `gh auth refresh -s read:packages`, `docker login ghcr.io`, then create the deployment clone `C:\deploy\cctv`, copy `.env` into it, run `watch.py --enroll` and register the scheduled task (README, CI/CD).
- Turn on Docker Desktop "Start Docker Desktop when you sign in" (owner).
- Raspberry Pis: the `kafka-webapp` package is private, so they cannot pull it yet (make it public in the package settings, or log them in). Not tested on a real Pi.
- Enrol more people: copy their photos to `FACIAL-RECOGNITION-DATASET/<person_id>/`, run `src/util/enrol_person.py` (it saves `vectors.parquet` and publishes a new Milvus version, D-030), add `front_face.jpg` to `DISPLAY-FACE-DATASET`, then `dvc add` and `dvc push`, and update the manifest.
- Map the producer-consumer runtime files to explicit mounts, replacing its whole-repo `.` mount.
- Fill the 4 null manifest values from the GPU host (commands are in the manifest's `unverified` block).

Do not touch:
- `STANDALONE-SERVICES/` upstream services (InsightFace-REST, Milvus, Kafka).
- Kafka-WebApp code from this repository: change it in its own repository.
- Never run a self-hosted Actions runner on this machine: it is also the dev box.
