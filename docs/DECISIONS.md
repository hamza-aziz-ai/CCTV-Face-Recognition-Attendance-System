# Decisions

One entry per meaningful decision, newest last. Each records the options considered, the choice, why, the trade-off, and when to revisit it.

## D-001: Bake application source into the Docker images
Date: 2026-10-30   Model: Claude Opus 5.5 with Codex gpt-6.1-sol (council)
Context: Most images held only dependencies; code was bind-mounted from the host at runtime, so a pushed image could not run on its own.
Options: 1) keep bind-mounts only  2) `COPY src/ src/` into every image  3) `COPY . .`
Chosen: 2
Why: Images become deployable artifacts for the registry. `src/` is about 600 KB. `COPY . .` would pull in datasets, git history and local config.
Trade-off: Images must be rebuilt for code changes. Development keeps the bind-mounts, which override the baked copy.
Revisit if: images are never deployed from a registry.

## D-002: Base image python:3.11-slim-bookworm, pinned by digest
Date: 2026-10-30   Model: Claude Opus 5.5 with Codex gpt-6.1-sol (council)
Context: All images used `python:3.8-slim-buster`. Buster's apt repositories moved to archive.debian.org (deb.debian.org returns 404), so `apt update` is expected to fail. Python 3.8 reached end of life in October 2024.
Options: 1) 3.8 on bookworm (same Python, new Debian)  2) 3.11 on bookworm  3) 3.12+
Chosen: 2
Why: It is a supported runtime, and every pinned requirement (numpy~=1.24.4, matplotlib~=3.7.5, uvicorn~=0.33, opencv 4.10, pymilvus 2.5) publishes 3.11 wheels. numpy 1.24 has no 3.12 wheels, which rules out option 3 without dependency bumps.
Trade-off: Runtime behaviour on 3.11 is verified only by builds, `pip check` and import smoke tests, not by a live pipeline run.
Revisit if: dependencies are bumped (then consider 3.12+), or a 3.11 runtime regression appears.

## D-003: Healthchecks use a Python socket probe, and fail for real
Date: 2026-10-30   Model: Claude Opus 5.5
Context: The healthcheck scripts ran `nc` (not present in slim images) and ended with `echo $?`, so they always exited 0. The API check probed 9090 inside the container, but the app listens on 8000 (9090 is only the host port).
Options: 1) install netcat in every image  2) a `python3 -c socket.create_connection` probe
Chosen: 2
Why: Python is already in every image, so no new package is needed. The probe's exit code is the script's exit code.
Trade-off: It checks that a port accepts connections, not that the service works end to end.
Revisit if: deployment automation needs readiness beyond the port (see the phase-two deployment criteria).

## D-004: Stop tracking master.env; ship master.env.example
Date: 2026-10-30   Model: Claude Opus 5.5 with Codex gpt-6.1-sol (council)
Context: `master.env` holds site configuration (INSTITUTE, IP_ADDRESS) and is rewritten in place by `set_configuration.sh` on every start.
Options: 1) keep it tracked  2) untrack it, add a template, and create the file on first run
Chosen: 2
Why: Site-specific values stay out of git and out of images. `set_configuration.sh` copies the template when the file is missing, so fresh clones still start.
Trade-off: Pulling this change on an existing host deletes the tracked `master.env`; the next `set_configuration.sh` run recreates it from the template and rewrites both values.
Revisit if: more site settings move into env files (consider one documented template for all).
Correction (2026-10-30): the original commit added the ignore rule but never ran `git rm --cached`, so `master.env` stayed tracked until v0.4.x. Tags up to then still contain it; the deployment watcher keeps the host's copy across checkouts so neither direction deletes or overwrites it.

## D-005: Keep camera configuration and datasets out of images
Date: 2026-10-30   Model: Claude Opus 5.5 with Codex gpt-6.1-sol (council)
Context: `src/Camera-Configuration/` holds per-site camera details; the dataset folders are large. Both live in the build context.
Options: 1) bake them in  2) exclude them via `.dockerignore` and mount them at runtime
Chosen: 2
Why: A registry image should not carry site camera details or face data. Compose already mounts them.
Trade-off: A container started without the mounts fails at import of `src/parameters.py`.
Revisit if: a single-site, self-contained image is ever required.

## D-006: CI gate without unit tests
Date: 2026-10-30   Model: Claude Opus 5.5 with Codex gpt-6.1-sol (council)
Context: The repo has no automated tests; the `src/util/test_*.py` files are manual scripts that need live services.
Options: 1) block on writing tests first  2) narrow lint + secret scan + compose validation + image build and smoke tests  3) a full ruff style ruleset
Chosen: 2
Why: These checks catch real breakage (syntax errors, undefined names, leaked secrets, broken builds, missing files) with zero false positives today. Option 3 would flood a legacy codebase with style noise.
Trade-off: There is no behavioural coverage, so recognition accuracy and service logic are untested.
Revisit if: unit tests are added; then add a pytest job to `ci`.

## D-007: Remove dead `del MULTIPROCESS_SHARED_BUFFER` blocks
Date: 2026-10-30   Model: Claude Opus 5.5
Context: The lint gate found F821 in `src/main.py` and `src/multicam_stream_consumer.py`. Deleting a module global inside a function without `global` always raises UnboundLocalError, which the surrounding `except` swallowed and logged.
Options: 1) add `global`  2) remove the blocks
Chosen: 2
Why: The process exits immediately afterwards, which frees the queue anyway. The code never worked and only produced a misleading log line.
Trade-off: None in behaviour; the "Error in Deleting Shared Queue" log line disappears.
Revisit if: never.

## D-008: GitHub Free plan: manual merges, native branch deletion
Date: 2026-10-30   Model: Claude Opus 5.5 with Codex gpt-6.1-sol (council)
Context: Branch rulesets and native auto-merge need GitHub Pro on private repos. The account is on Free.
Options: 1) upgrade to Pro  2) a label-triggered merge workflow  3) manual merges with the `ci` check visible
Chosen: 3, plus the "Automatically delete head branches" setting (available on all plans)
Why: A merge bot without enforced protection can merge a head commit the checks never covered, which is false safety.
Trade-off: There is no AutoMerge until Pro.
Revisit if: the account upgrades to Pro; then add a ruleset requiring `ci` and enable opt-in auto-merge.

## D-009: Declare the ROI app's dependencies
Date: 2026-10-30   Model: Claude Opus 5.5
Context: `Custom-ROI-Provisioning/requirements.txt` has been empty since the first commit, so `roi.Dockerfile` installed nothing and the image could not import flask or cv2. The CI smoke test found this.
Options: 1) drop ROI from CI  2) declare its imports
Chosen: 2, with flask~=3.1.0, numpy~=1.24.4, opencv-python~=4.10.0.84, python-dotenv~=1.0.1
Why: The app imports exactly these. Every pin except flask matches the other services. Flask (Pallets project) is the only package new to the repo; 3.1 is the current stable line and supports Python 3.11.
Trade-off: The ROI app itself has not been run end to end on these versions.
Revisit if: the ROI UI shows Flask 3.x incompatibilities.

## D-010: Split production and development compose files
Date: 2026-10-30   Model: Claude Opus 5.5 with Codex gpt-6.1-sol (council)
Context: `docker-compose-main.yml` built images in place and bind-mounted `./src` over them. With source now baked in (D-001), production should run exactly what was built.
Options: 1) keep one file with build and mounts  2) base file without builds or source mounts, plus a `docker-compose.dev.yml` override  3) a separate full production file
Chosen: 2, and remove `build-docker-images.sh`: `docker compose -f docker-compose-main.yml -f docker-compose.dev.yml build` replaces it.
Why: There is one source of truth for services. The override only adds builds and live-code mounts, and the merged config equals the old behaviour (verified with `docker compose config`).
Trade-off: Hosts must rebuild after pulling (the old `v-beta` images contain no code). The producer-consumer still mounts the whole repo, because its runtime file set (camera config, frames, datasets) is not yet mapped to explicit mounts.
Revisit if: images come from the registry (step 5). Then the base file references pinned digests, and the producer-consumer gets explicit mounts.

## D-011: Dependabot version updates for actions and base images only
Date: 2026-10-30   Model: Claude Opus 5.5
Context: Workflow actions are pinned to commit SHAs and the base image to a digest; neither updates itself. The council plan named github-actions only.
Options: 1) github-actions only  2) github-actions + docker  3) also pip version updates
Chosen: 2, weekly, one grouped PR per ecosystem
Why: A base-image digest goes stale for the same reason action SHAs do, and misses OS security patches. Python vulnerabilities already arrive through Dependabot security updates. Pip version updates across 8 requirement files would be noise without tests.
Trade-off: Up to two automated PRs a week to review and merge by hand (manual merges on the Free plan).
Revisit if: unit tests exist (consider pip updates), or the account moves to Pro (consider auto-merge for patch updates).

## D-012: Model manifest with a CI drift check
Date: 2026-10-30   Model: Claude Opus 5.5 with Codex gpt-6.1-sol (council)
Context: There is no training loop. What can change behaviour is the external models (InsightFace-REST TensorRT engines), thresholds, the Milvus index and search settings, and the datasets. None of this was recorded in one place, and the README model names were unchecked.
Options: 1) MLflow or a model registry  2) image labels only  3) a hand-maintained `mlops/model-manifest.json`, checked against source in CI
Chosen: 3
Why: MLflow needs a training/eval loop this repo does not have. Labels cannot be checked. A manifest plus `mlops/check_manifest.py` (reads `parameters.py`, `standalone-services.env`, `models.json`, `milvus_server.py` and the `.dvc` files as text) fails CI the moment the manifest and the code disagree.
Trade-off: Host-only facts (TensorRT engine sha256, InsightFace image digest, embedding snapshot) cannot be derived in CI. They stay `null` with instructions, and `--release` fails until they are filled from the GPU host. ONNX md5 values are the ones InsightFace-REST expects; the files actually deployed are not verified.
Revisit if: a training or evaluation loop is added (then consider a registry), or models move to a different inference service.

## D-013: Workflow-based auto-merge on GitHub Free (supersedes D-008)
Date: 2026-10-30   Model: Claude Opus 5.5 (pattern from the Medical-ChatBot and HalalLens sessions)
Context: The owner wants every PR to merge into main by itself once all CI passes, with its branch deleted. The repo is private on GitHub Free, so there are no rulesets and no native auto-merge.
Options: 1) upgrade to Pro and use native auto-merge  2) a label-triggered merge  3) a workflow that merges on CI success, checked against the exact head commit
Chosen: 3: `.github/workflows/automerge.yml`, triggered by `workflow_run` of `ci` (and by hand).
Why: It needs no PAT and no paid plan, and fixes the two problems that made D-008 reject a merge bot:
- It checks the exact head commit: it merges only when the `ci` check succeeded and every other check on the PR's head commit succeeded, was skipped or was neutral, using `gh pr merge --match-head-commit`, so a commit pushed after CI ran is never merged unchecked.
- A PR cannot change the rule: it never runs on `pull_request`, so the PR's own copy of the workflow never runs with a write token; `workflow_run` always runs main's copy.
- Forks and drafts are skipped. After a merge it sweeps again (up to 5 times) so PRs stacked on the merged branch, which GitHub retargets to main without re-running CI, merge as well.
Trade-off: Nothing stops a direct push to main (no branch protection on Free). CI ran against the base as it was when the PR last changed, not against the newest main. Dependabot PRs merge too once CI passes, and so reach releases without review.
Revisit if: the account moves to Pro (switch to a ruleset requiring `ci` and native auto-merge), or a bad auto-merge reaches main.

## D-014: Automatic releases from Conventional Commit PR titles, chained from auto-merge
Date: 2026-10-30   Model: Claude Opus 5.5 (pattern from the Medical-ChatBot session)
Context: The owner wants a release whenever merged work calls for a version bump. Merges made by auto-merge use GITHUB_TOKEN, and those start no push workflows.
Options: 1) release-please (release PR)  2) a home-made bump from the merged titles, started by auto-merge via workflow_dispatch  3) one release per merge (Medical-ChatBot)
Chosen: 2: `.github/workflows/release.yml`. Squash merges make each commit subject a PR title:
- `type!:` or a `BREAKING CHANGE` footer → major
- `feat` → minor
- `fix` or `perf` → patch
- anything else (docs, ci, chore, build, Dependabot's `build(deps)`) → no release
Auto-merge starts it after merging. It re-runs the full `ci` on the exact commit, then creates the tag through the API and a GitHub Release with generated notes and `model-manifest.json` attached.
Why: Release-please opens its release PR with GITHUB_TOKEN, which gets no CI, so that PR would need a PAT to auto-merge. Option 2 needs no PAT, no release PR and no extra config. Option 3 releases every docs or CI change.
Trade-off:
- PR titles must follow Conventional Commits, and nothing enforces it yet; a wrongly typed title skips or under-bumps a release.
- No images are pushed: the deployment host is this machine, which builds from the tag. The registry push is deferred until DockerHub is configured or a separate host exists.
- Null host-only manifest values are listed as unverified but do not block a release; drift does block.
Revisit if: wrong bumps happen (add a PR-title check to `ci`), images must be pulled by another host (add a registry push), or the A100 host is built (make `check_manifest.py --release` blocking).

## D-015: Per-host GPU profiles, starting with the RTX 4050 laptop
Date: 2026-10-30   Model: Claude Opus 5.5
Context: This laptop (RTX 4050, 6 GB, no MIG) is for now the dev and the deployment host. `standalone-services.env` pins InsightFace-REST, Milvus and liveness to A100 MIG slices (`7:0`..`7:4`) with A100-sized engine batches, so nothing GPU-bound can start here.
Options: 1) edit `standalone-services.env` for the laptop  2) a gitignored local override  3) committed per-host profiles in `STANDALONE-SERVICES/hosts/`, selected by `HOST_PROFILE` in the root `.env`
Chosen: 3: `hosts/laptop-rtx4050.env`. It places both InsightFace containers and Milvus on GPU 0 (the nginx load balancer keeps its two backends), uses one worker, and sets batches to det 8 / rec 16. `deploy_trt_multi-gpu.sh` and `start_standalone_services.sh` load the profile after the base file and fail loudly if the named profile is missing.
Why: The A100 defaults stay intact for the real site. The profile is reviewed in git and is the same on every deploy (the watcher relies on that). Option 2 would hide the host's config from review.
Trade-off: The batch sizes are untested guesses for 6 GB shared by two TensorRT containers plus Milvus; they must be tuned after the first bring-up. Models, detection threshold and ports are unchanged, so recognition behaviour matches the A100 config. Engine batch size does not change results, so the model manifest keeps describing the base config.
Revisit if: the first bring-up runs out of GPU memory (drop to one InsightFace container and a single-backend nginx config), or another host type is added (add a profile).

## D-016: Pull-based deployment watcher on the deployment host
Date: 2026-10-30   Model: Claude Opus 5.5 (lessons from the Medical-ChatBot and HalalLens sessions)
Context: The owner wants the deployment server to update itself when a release is published. For now the deployment host is this Windows laptop, which is also the dev machine.
Options: 1) a self-hosted Actions runner deploying on release  2) Watchtower  3) a poller run by Task Scheduler from a dedicated deploy clone
Chosen: 3: `deploy/watch.py`, stdlib Python, every 10 minutes through `pythonw` (no console window).
Why:
- A self-hosted runner with Docker access on the dev box would hand host-admin power to workflow code.
- Watchtower cannot roll back to a known tag or run the repo's build.
- The poller needs no inbound access and no extra credentials (it uses the owner's `gh` login).
- It records a release as current only after `up --wait` and an HTTP smoke test pass, rolls back to the last good tag on failure, and never retries a failed release unattended.
- It never restarts a stack the owner stopped, and never touches the dev checkout.
- Images are tagged per release (`IMAGE_TAG` in `docker-compose-main.yml`), so a rollback reuses the previous release's images instead of rebuilding over them.
Trade-off:
- It runs only while the owner is signed in and Docker Desktop is up.
- Each deploy restarts the producer-consumer, and `main.py` deletes Kafka topics on start (pending feedback may be lost).
- The rollback cannot undo data changes in Postgres or Milvus.
- Dev and deployed stacks share container names and ports, so only one runs at a time.
- It deploys whatever reached `main` through auto-merge, including Dependabot updates once they cause a release.
- The datasets are not present on this host yet (DVC not pulled).
Revisit if: a separate deployment host exists (pull registry images by digest instead of building), or a deploy loses data (add a backup step before `up`).

## D-017: Publish release images to GitHub Packages (ghcr.io); the watcher pulls them (amends D-014, D-016)
Date: 2026-10-30   Model: Claude Opus 5.5
Context: v0.1.0 and v0.2.0 were released with no images. The owner expects each release to ship its Docker images as packages.
Options: 1) DockerHub (needs an account token as a repo secret)  2) GitHub Container Registry with the workflow's own `GITHUB_TOKEN`  3) keep building on the deployment host
Chosen: 2. A new `images` job in `release.yml` runs after the release CI and before tagging. It builds with both compose files and runs `docker compose push`, which pushes only services with a build section (the 7 app images, not postgres). Images are `ghcr.io/hamza-aziz-ai/cctv-face-recognition-<service>:<tag>`, named in `docker-compose-main.yml`. Every Dockerfile carries `org.opencontainers.image.source`, so each package links to this repository and inherits its private access. The watcher now runs `up --pull missing --no-build` and no longer builds.
Why:
- No new secret or account: `GITHUB_TOKEN` gets `packages: write` in that one job only.
- The deployed image is the one CI built, not a rebuild on the laptop.
- A release is never published without its images, because tagging waits for the push.
- GHCR storage and transfer are currently free (GitHub's billing docs; GitHub promises a month's notice before that changes).
- Tags are never moved, so `--pull missing` downloads a release once and a rollback reuses it offline.
Trade-off:
- The deployment host must sign in to ghcr.io once (`gh auth refresh -s read:packages`, then `docker login`); without it every deploy fails and rolls back.
- The images are rebuilt in the release run instead of reusing the CI build. The bytes can differ from what the CI smoke test ran; same Dockerfiles, pinned base digest.
- v0.1.0 and v0.2.0 have no images; the first deployable release is v0.3.0.
- The ROI app has no compose service, so its image is built in CI but not published.
- DockerHub stays unused.
- Pushes run one at a time (`--parallel 1`): the first v0.3.0 release run pushed all 7 in parallel and ghcr.io answered "denied" for a random subset, twice.
Revisit if: the free GHCR policy changes, the repo goes public (DockerHub mirror for discoverability), or a CI-to-release digest match is required (push from the CI image job instead).

## D-018: Containers restart themselves; headless operation planned, not built
Date: 2026-10-30   Model: Claude Opus 5.5
Context: The owner wants the standalone services (InsightFace-REST, Milvus, Kafka) and the app stack to come back on their own after a crash or a reboot, with nobody starting them. PTZ-Camera-Classroom-Attendance-System uses the same InsightFace-REST and Milvus instances (ports 6385 and 19530; it has no copy of its own), and both projects will be merged later.
Options: 1) restart policies, with Docker Desktop starting at sign-in  2) a watchdog that re-runs the start scripts  3) Docker Engine as a service in WSL2, running without sign-in
Chosen: 1 now. `restart: unless-stopped` on every Milvus, Kafka and main-stack container, and `--restart unless-stopped` on the InsightFace workers and their nginx. The InsightFace deploy script now removes an old container of the same name whether it is running or stopped, so a redeploy no longer collides with a stopped one. The manifest records the InsightFace-REST upstream: SthPhoenix/InsightFace-REST at `e9b85b9` (2024-11-02), with local changes to its two Dockerfiles and `requirements.txt` (the vendored `src/` matches no upstream commit exactly; `e9b85b9` differs in only those 3 files).
Why: Docker brings the containers back after a crash and whenever its daemon starts, with no extra code. `unless-stopped` keeps a deliberate `docker stop` in force, which the watcher relies on ("never start a stack the owner stopped").
Trade-off:
- Docker Desktop runs only while the owner is signed in to Windows ("Start Docker Desktop when you sign in" must be on).
- A container that is running but unhealthy is not restarted.
- The first start is still manual (`start_standalone_services.sh`): it builds the InsightFace image and the TensorRT engines.
Headless plan (option 3, not built): Docker Engine plus the NVIDIA Container Toolkit in a WSL2 Ubuntu with systemd; Docker Desktop off; a Task Scheduler task "at startup, whether signed in or not" that starts the distro and keeps it alive (`vmIdleTimeout=-1` in `.wslconfig`); the watcher moves into WSL as a systemd timer, with a notification other than `msg`. Containers then restart when dockerd starts at boot.
Revisit if: the host must run unattended through reboots (build the headless plan), or the deployment moves to a Linux GPU server (restart policies alone are enough there).

## D-019: DVC remote on a dedicated MinIO (dataset store)
Date: 2026-10-30   Model: Claude Opus 5.5
Context: The face datasets (FACIAL-RECOGNITION-DATASET: 22.5 GB, 54,809 files; DISPLAY-FACE-DATASET: 1.6 GB) are tracked by DVC, but the remote (Google Drive, `face-recognition-dataset-gdrive`) lived only in a git-ignored `.dvc/config`, so no other machine could pull them. The owner chose MinIO as the remote.
Options: 1) a new bucket in Milvus's MinIO  2) a dedicated MinIO service  3) keep Google Drive
Chosen: 2. `STANDALONE-SERVICES/Dataset-Store`: `pgsty/minio` (same pinned build as Milvus's), S3 API on 9010, console on 9011, `restart: unless-stopped`. Root login and the data folder come from `.env` (`DATASET_STORE_USER`, `DATASET_STORE_PASSWORD`, `DATASET_STORE_DIR`, all required); a one-shot container creates the `dvc` bucket. `start_standalone_services.sh` and `stop_standalone_services.sh` manage it. `.dvc/config` is tracked again with the default remote `minio` (`s3://dvc`, endpoint `http://localhost:9010`); credentials and another host's endpoint go in `.dvc/config.local` (git-ignored).
Why:
- Milvus's MinIO uses the default `minioadmin` login and keeps its data under the repo folder; resetting Milvus or deleting a checkout would take the datasets with it.
- A separate login and a data folder outside the repo keep the face images (biometric personal data) apart from the vector store.
- S3 over the LAN needs no Google account or browser login, so CI and other hosts can pull with a key.
Trade-off:
- DVC uses the MinIO root login; a read-only DVC user for consumers is not set up yet.
- No encryption at rest beyond the host disk (BitLocker); MinIO server-side encryption needs a KMS.
- The datasets are still on Google Drive only: someone with that remote must pull from it and push to `minio`.
- The store lives on this laptop: no backup copy yet.
Revisit if: a second machine needs the data regularly (read-only user, endpoint by hostname), or the store holds the only copy (add a replica or backup).

## D-020: PostgreSQL 12 to 18.6
Date: 2026-10-30   Model: Claude Opus 5.5
Context: The stack ran `postgres:12-bullseye`; PostgreSQL 12 is out of support. The owner asked for the latest stable release. 18.6 is the current stable (`latest` points to it); 19 is a release candidate.
Options: 1) `postgres:latest`  2) pin `postgres:18.6-trixie`  3) 17.11
Chosen: 2, with `psycopg2-binary` 2.9.10 to 2.9.13. The 18 images keep data in `/var/lib/postgresql/18/docker` and expect the volume at `/var/lib/postgresql`, so the stack now mounts a new host folder, `/workspace/database/postgresql18/cctv-face-recognition`, at that path.
Why: A pinned tag keeps every deploy identical; `latest` would jump to 19 on its release. A new folder never lets an 18 server open 12 data files, and leaves the 12 data in place for a rollback to v0.5.x.
Trade-off: A site with existing data starts with an empty database until it is migrated. Upgrade runbook, before deploying this release on such a site:
1. With the old stack running: `docker exec cctv-face-recognition-postgresql-database pg_dumpall -U "$POSTGRES_USER" > pg12-dump.sql`
2. Deploy this release (the new folder is created empty and initialised).
3. `docker exec -i cctv-face-recognition-postgresql-database psql -U "$POSTGRES_USER" -d postgres < pg12-dump.sql`
4. Check row counts, then remove `/workspace/database/postgresql/cctv-face-recognition` once nothing needs a rollback.
Revisit if: PostgreSQL 19 is released and has been stable for a minor release or two.

