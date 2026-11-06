# Decisions

One entry per meaningful decision, newest last. Each records the options considered, the choice, why, the trade-off, and when to revisit it.

## D-001: Bake application source into the Docker images
Date: 2026-10-30   Model: Claude Opus 5.5 with Codex GPT-6.1 Sol (council)
Context: Most images held only dependencies; code was bind-mounted from the host at runtime, so a pushed image could not run on its own.
Options:

1. keep bind-mounts only
2. `COPY src/ src/` into every image
3. `COPY . .`

Chosen: 2
Why: Images become deployable artifacts for the registry. `src/` is about 600 KB. `COPY . .` would pull in datasets, git history and local config.
Trade-off: Images must be rebuilt for code changes. Development keeps the bind-mounts, which override the baked copy.
Revisit if: images are never deployed from a registry.

## D-002: Base image python:3.11-slim-bookworm, pinned by digest
Date: 2026-10-30   Model: Claude Opus 5.5 with Codex GPT-6.1 Sol (council)
Context: All images used `python:3.8-slim-buster`. Buster's apt repositories moved to archive.debian.org (deb.debian.org returns 404), so `apt update` is expected to fail. Python 3.8 reached end of life in October 2024.
Options:

1. 3.8 on bookworm (same Python, new Debian)
2. 3.11 on bookworm
3. 3.12+

Chosen: 2
Why: It is a supported runtime, and every pinned requirement (numpy~=1.24.4, matplotlib~=3.7.5, uvicorn~=0.33, opencv 4.10, pymilvus 2.5) publishes 3.11 wheels. numpy 1.24 has no 3.12 wheels, which rules out option 3 without dependency bumps.
Trade-off: Runtime behavior on 3.11 is verified only by builds, `pip check` and import smoke tests, not by a live pipeline run.
Revisit if: dependencies are bumped (then consider 3.12+), or a 3.11 runtime regression appears.

## D-003: Health checks use a Python socket probe, and fail for real
Date: 2026-10-30   Model: Claude Opus 5.5
Context: The health check scripts ran `nc` (not present in slim images) and ended with `echo $?`, so they always exited 0. The API check probed 9090 inside the container, but the app listens on 8000 (9090 is only the host port).
Options:

1. install netcat in every image
2. a `python3 -c socket.create_connection` probe

Chosen: 2
Why: Python is already in every image, so no new package is needed. The probe's exit code is the script's exit code.
Trade-off: It checks that a port accepts connections, not that the service works end to end.
Revisit if: deployment automation needs readiness beyond the port (see the phase-two deployment criteria).

## D-004: Stop tracking master.env; ship master.env.example
Date: 2026-10-30   Model: Claude Opus 5.5 with Codex GPT-6.1 Sol (council)
Context: `master.env` holds site configuration (INSTITUTE, IP_ADDRESS) and is rewritten in place by `set_configuration.sh` on every start.
Options:

1. keep it tracked
2. untrack it, add a template, and create the file on first run

Chosen: 2
Why: Site-specific values stay out of git and out of images. `set_configuration.sh` copies the template when the file is missing, so fresh clones still start.
Trade-off: Pulling this change on an existing host deletes the tracked `master.env`; the next `set_configuration.sh` run recreates it from the template and rewrites both values.
Revisit if: more site settings move into env files (consider one documented template for all).
Correction (2026-10-30): the original commit added the ignore rule but never ran `git rm --cached`, so `master.env` stayed tracked until v0.4.x. Tags up to then still contain it; the deployment watcher keeps the host's copy across checkouts so neither direction deletes or overwrites it.

## D-005: Keep camera configuration and datasets out of images
Date: 2026-10-30   Model: Claude Opus 5.5 with Codex GPT-6.1 Sol (council)
Context: `src/Camera-Configuration/` holds per-site camera details; the dataset folders are large. Both live in the build context.
Options:

1. bake them in
2. exclude them via `.dockerignore` and mount them at runtime

Chosen: 2
Why: A registry image should not carry site camera details or face data. Compose already mounts them.
Trade-off: A container started without the mounts fails at import of `src/parameters.py`.
Revisit if: a single-site, self-contained image is ever required.

## D-006: CI gate without unit tests
Date: 2026-10-30   Model: Claude Opus 5.5 with Codex GPT-6.1 Sol (council)
Context: The repo has no automated tests; the `src/util/test_*.py` files are manual scripts that need live services.
Options:

1. block on writing tests first
2. narrow lint + secret scan + compose validation + image build and smoke tests
3. a full ruff style ruleset

Chosen: 2
Why: These checks catch real breakage (syntax errors, undefined names, leaked secrets, broken builds, missing files) with zero false positives today. Option 3 would flood a legacy codebase with style noise.
Trade-off: There is no behavioral coverage, so recognition accuracy and service logic are untested.
Revisit if: unit tests are added; then add a pytest job to `ci`.

## D-007: Remove dead `del MULTIPROCESS_SHARED_BUFFER` blocks
Date: 2026-10-30   Model: Claude Opus 5.5
Context: The lint gate found F821 in `src/main.py` and `src/multicam_stream_consumer.py`. Deleting a module global inside a function without `global` always raises UnboundLocalError, which the surrounding `except` swallowed and logged.
Options:

1. add `global`
2. remove the blocks

Chosen: 2
Why: The process exits immediately afterward, which frees the queue anyway. The code never worked and only produced a misleading log line.
Trade-off: None in behavior; the "Error in Deleting Shared Queue" log line disappears.
Revisit if: never.

## D-008: GitHub Free plan: manual merges, native branch deletion
Date: 2026-10-30   Model: Claude Opus 5.5 with Codex GPT-6.1 Sol (council)
Context: Branch rulesets and native auto-merge need GitHub Pro on private repos. The account is on Free.
Options:

1. upgrade to Pro
2. a label-triggered merge workflow
3. manual merges with the `ci` check visible

Chosen: 3, plus the "Automatically delete head branches" setting (available on all plans)
Why: A merge bot without enforced protection can merge a head commit the checks never covered, which is false safety.
Trade-off: There is no AutoMerge until Pro.
Revisit if: the account upgrades to Pro; then add a ruleset requiring `ci` and enable opt-in auto-merge.

## D-009: Declare the ROI app's dependencies
Date: 2026-10-30   Model: Claude Opus 5.5
Context: `Custom-ROI-Provisioning/requirements.txt` has been empty since the first commit, so `roi.Dockerfile` installed nothing and the image could not import flask or cv2. The CI smoke test found this.
Options:

1. drop ROI from CI
2. declare its imports

Chosen: 2, with flask~=3.1.0, numpy~=1.24.4, opencv-python~=4.10.0.84, python-dotenv~=1.0.1
Why: The app imports exactly these. Every pin except flask matches the other services. Flask (Pallets project) is the only package new to the repo; 3.1 is the current stable line and supports Python 3.11.
Trade-off: The ROI app itself has not been run end to end on these versions.
Revisit if: the ROI UI shows Flask 3.x incompatibilities.

## D-010: Split production and development compose files
Date: 2026-10-30   Model: Claude Opus 5.5 with Codex GPT-6.1 Sol (council)
Context: `docker-compose-main.yml` built images in place and bind-mounted `./src` over them. With source now baked in (D-001), production should run exactly what was built.
Options:

1. keep one file with build and mounts
2. base file without builds or source mounts, plus a `docker-compose.dev.yml` override
3. a separate full production file

Chosen: 2, and remove `build-docker-images.sh`: `docker compose -f docker-compose-main.yml -f docker-compose.dev.yml build` replaces it.
Why: There is one source of truth for services. The override only adds builds and live-code mounts, and the merged config equals the old behavior (verified with `docker compose config`).
Trade-off: Hosts must rebuild after pulling (the old `v-beta` images contain no code). The producer-consumer still mounts the whole repo, because its runtime file set (camera config, frames, datasets) is not yet mapped to explicit mounts.
Revisit if: images come from the registry (step 5). Then the base file references pinned digests, and the producer-consumer gets explicit mounts.

## D-011: Dependabot version updates for actions and base images only
Date: 2026-10-30   Model: Claude Opus 5.5
Context: Workflow actions are pinned to commit SHAs and the base image to a digest; neither updates itself. The council plan named GitHub Actions only.
Options:

1. github-actions only
2. github-actions + docker
3. also pip version updates

Chosen: 2, weekly, one grouped PR per ecosystem
Why: A base-image digest goes stale for the same reason action SHAs do, and misses OS security patches. Python vulnerabilities already arrive through Dependabot security updates. Pip version updates across 8 requirement files would be noise without tests.
Trade-off: Up to two automated PRs a week to review and merge by hand (manual merges on the Free plan).
Revisit if: unit tests exist (consider pip updates), or the account moves to Pro (consider auto-merge for patch updates).

## D-012: Model manifest with a CI drift check
Date: 2026-10-30   Model: Claude Opus 5.5 with Codex GPT-6.1 Sol (council)
Context: There is no training loop. What can change behavior is the external models (InsightFace-REST TensorRT engines), thresholds, the Milvus index and search settings, and the datasets. None of this was recorded in one place, and the README model names were unchecked.
Options:

1. MLflow or a model registry
2. image labels only
3. a hand-maintained `mlops/model-manifest.json`, checked against source in CI

Chosen: 3
Why: MLflow needs a training/eval loop this repo does not have. Labels cannot be checked. A manifest plus `mlops/check_manifest.py` (reads `parameters.py`, `standalone-services.env`, `models.json`, `milvus_server.py` and the `.dvc` files as text) fails CI the moment the manifest and the code disagree.
Trade-off: Host-only facts (TensorRT engine sha256, InsightFace image digest, embedding snapshot) cannot be derived in CI. They stay `null` with instructions, and `--release` fails until they are filled from the GPU host. ONNX md5 values are the ones InsightFace-REST expects; the files actually deployed are not verified.
Revisit if: a training or evaluation loop is added (then consider a registry), or models move to a different inference service.

## D-013: Workflow-based auto-merge on GitHub Free (supersedes D-008)
Date: 2026-10-30   Model: Claude Opus 5.5 (pattern from the Medical-ChatBot and HalalLens sessions)
Context: The owner wants every PR to merge into main by itself once all CI passes, with its branch deleted. The repo is private on GitHub Free, so there are no rulesets and no native auto-merge.
Options:

1. upgrade to Pro and use native auto-merge
2. a label-triggered merge
3. a workflow that merges on CI success, checked against the exact head commit

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
Options:

1. release-please (release PR)
2. a home-made bump from the merged titles, started by auto-merge via workflow_dispatch
3. one release per merge (Medical-ChatBot)

Chosen: 2: `.github/workflows/release.yml`. Squash merges make each commit subject a PR title:
- `type!:` or a `BREAKING CHANGE` footer → major
- `feat` → minor
- `fix` or `perf` → patch
- anything else (docs, ci, chore, build, Dependabot's `build(deps)`) → no release
Auto-merge starts it after merging. It re-runs the full `ci` on the exact commit, then creates the tag through the API and a GitHub Release with generated notes and `model-manifest.json` attached.
Why: Release-please opens its release PR with GITHUB_TOKEN, which gets no CI, so that PR would need a PAT to auto-merge. Option 2 needs no PAT, no release PR and no extra config. Option 3 releases every doc or CI change.
Trade-off:
- PR titles must follow Conventional Commits, and nothing enforces it yet; a wrongly typed title skips or under-bumps a release.
- No images are pushed: the deployment host is this machine, which builds from the tag. The registry push is deferred until DockerHub is configured or a separate host exists.
- Null host-only manifest values are listed as unverified but do not block a release; drift does block.
Revisit if: wrong bumps happen (add a PR-title check to `ci`), images must be pulled by another host (add a registry push), or the A100 host is built (make `check_manifest.py --release` blocking).

## D-015: Per-host GPU profiles, starting with the RTX 4050 laptop
Date: 2026-10-30   Model: Claude Opus 5.5
Context: This laptop (RTX 4050, 6 GB, no MIG) is for now the dev and the deployment host. `standalone-services.env` pins InsightFace-REST, Milvus and liveness to A100 MIG slices (`7:0`..`7:4`) with A100-sized engine batches, so nothing GPU-bound can start here.
Options:

1. edit `standalone-services.env` for the laptop
2. a gitignored local override
3. committed per-host profiles in `STANDALONE-SERVICES/hosts/`, selected by `HOST_PROFILE` in the root `.env`

Chosen: 3: `hosts/laptop-rtx4050.env`. It places both InsightFace containers and Milvus on GPU 0 (the nginx load balancer keeps its two backends), uses one worker, and sets batches to det 8 / rec 16. `deploy_trt_multi-gpu.sh` and `start_standalone_services.sh` load the profile after the base file and fail loudly if the named profile is missing.
Why: The A100 defaults stay intact for the real site. The profile is reviewed in git and is the same on every deploy (the watcher relies on that). Option 2 would hide the host's config from review.
Trade-off: The batch sizes are untested guesses for 6 GB shared by two TensorRT containers plus Milvus; they must be tuned after the first bring-up. Models, detection threshold and ports are unchanged, so recognition behavior matches the A100 config. Engine batch size does not change results, so the model manifest keeps describing the base config.
Revisit if: the first bring-up runs out of GPU memory (drop to one InsightFace container and a single-backend nginx config), or another host type is added (add a profile).

## D-016: Pull-based deployment watcher on the deployment host
Date: 2026-10-30   Model: Claude Opus 5.5 (lessons from the Medical-ChatBot and HalalLens sessions)
Context: The owner wants the deployment server to update itself when a release is published. For now the deployment host is this Windows laptop, which is also the dev machine.
Options:

1. a self-hosted Actions runner deploying on release
2. Watchtower
3. a poller run by Task Scheduler from a dedicated deployment clone

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
Revisit if: a separate deployment host exists (pull registry images by digest instead of building), or a deployment loses data (add a backup step before `up`).

## D-017: Publish release images to GitHub Packages (ghcr.io); the watcher pulls them (amends D-014, D-016)
Date: 2026-10-30   Model: Claude Opus 5.5
Context: v0.1.0 and v0.2.0 were released with no images. The owner expects each release to ship its Docker images as packages.
Options:

1. DockerHub (needs an account token as a repo secret)
2. GitHub Container Registry with the workflow's own `GITHUB_TOKEN`
3. keep building on the deployment host

Chosen: 2. A new `images` job in `release.yml` runs after the release CI and before tagging. It builds with both compose files and runs `docker compose push`, which pushes only services with a build section (the 7 app images, not Postgres). Images are `ghcr.io/hamza-aziz-ai/cctv-face-recognition-<service>:<tag>`, named in `docker-compose-main.yml`. Every Dockerfile carries `org.opencontainers.image.source`, so each package links to this repository and inherits its private access. The watcher now runs `up --pull missing --no-build` and no longer builds.
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
Options:

1. restart policies, with Docker Desktop starting at sign-in
2. a watchdog that re-runs the start scripts
3. Docker Engine as a service in WSL2, running without sign-in

Chosen: 1 now. `restart: unless-stopped` on every Milvus, Kafka and main-stack container, and `--restart unless-stopped` on the InsightFace workers and their nginx. The InsightFace deploy script now removes an old container of the same name whether it is running or stopped, so a redeployment no longer collides with a stopped one. The manifest records the InsightFace-REST upstream: SthPhoenix/InsightFace-REST at `e9b85b9` (2024-11-02), with local changes to its two Dockerfiles and `requirements.txt` (the vendored `src/` matches no upstream commit exactly; `e9b85b9` differs in only those 3 files).
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
Options:

1. a new bucket in Milvus's MinIO
2. a dedicated MinIO service
3. keep Google Drive

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
Options:

1. `postgres:latest`
2. pin `postgres:18.6-trixie`
3. 17.11

Chosen: 2, with `psycopg2-binary` 2.9.10 to 2.9.13. The 18 images keep data in `/var/lib/postgresql/18/docker` and expect the volume at `/var/lib/postgresql`, so the stack now mounts a new host folder, `/workspace/database/postgresql18/cctv-face-recognition`, at that path.
Why: A pinned tag keeps every deploy identical; `latest` would jump to 19 on its release. A new folder never lets an 18 server open 12 data files, and leaves the 12 data in place for a rollback to v0.5.x.
Trade-off: A site with existing data starts with an empty database until it is migrated. Upgrade runbook, before deploying this release on such a site:
1. With the old stack running: `docker exec cctv-face-recognition-postgresql-database pg_dumpall -U "$POSTGRES_USER" > pg12-dump.sql`
2. Deploy this release (the new folder is created empty and initialized).
3. `docker exec -i cctv-face-recognition-postgresql-database psql -U "$POSTGRES_USER" -d postgres < pg12-dump.sql`
4. Check row counts, then remove `/workspace/database/postgresql/cctv-face-recognition` once nothing needs a rollback.
Revisit if: PostgreSQL 19 is released and has been stable for a minor release or two.

## D-021: Confluent Platform 7.8 to 8.4.0, community edition
Date: 2026-10-30   Model: Claude Opus 5.5
Context: The Kafka stack ran Confluent 7.8.0 images. The owner asked for the latest stable release, pointing at cp-all-in-one v8.4.0. That file has two editions: the enterprise one runs the commercial Confluent Server (`cp-server`) and Control Center next-gen, which needs a license key (a free developer license covers a single broker), and its Prometheus takes port 9090 (the API's port).
Options:

1. enterprise cp-all-in-one 8.4.0
2. community cp-all-in-one 8.4.0
3. broker only

Chosen: 2 (owner's choice). `STANDALONE-SERVICES/Confluent-Kafka/docker-compose.yml` follows `cp-all-in-one-community/docker-compose.yml` at v8.4.0: broker `cp-kafka:8.4.0` (Apache Kafka 4.x, KRaft), Schema Registry, Connect (`kafka-connect-datagen`), ksqlDB, REST Proxy and Flink. Local changes: the broker advertises `${IP_ADDRESS}` instead of localhost, and every service restarts unless stopped. Client `confluent-kafka` 2.7.0 to 2.16.1.
Why: Free broker with no license clock; the app only uses the broker. Our broker settings were already KRaft and carry over unchanged.
Trade-off: No Control Center UI. Flink adds three containers the app does not use. The 7.8 `ksqldb-cli`, `ksql-datagen` and legacy Control Center have no 8.4.0 counterpart in the community file and were removed. Topic data lived in `/tmp` inside the broker and was lost on recreation; D-028 moved it to a volume.
Revisit if: Kafbat UI (`127.0.0.1:8085`, added 2026-10-31) falls short (Control Center next-gen needs a license key), or the unused tools cost too much memory (drop to broker only).

## D-022: Milvus 2.5.1 to 3.0.5, following the official compose file
Date: 2026-10-30   Model: Claude Opus 5.5
Context: The owner asked for the latest stable Milvus and pointed at the official standalone compose file of the 3.0 line. The newest release is v3.0.5 (2026-10), newer than the v3.0.3 linked.
Options:

1. stay on 2.6.x
2. 3.0.5 with our old compose
3. 3.0.5 following its official GPU compose file

Chosen: 3. `STANDALONE-SERVICES/Milvus-Vector-Database/docker-compose.yml` follows `milvus-standalone-docker-compose-gpu.yaml` from the v3.0.5 release, images pinned by digest: `milvusdb/milvus:v3.0.5-gpu`, `quay.io/coreos/etcd:v3.5.25` and the Milvus-tested `milvusdb/minio:RELEASE.2024-12-18T13-15-44Z` (published by the Milvus project; replaces `pgsty/minio` here, the dataset store keeps `pgsty/minio`). It adds the official `milvus-volume-init` step, because 3.0 runs as the non-root user `milvus`. Local changes: GPU from `MILVUS_GPU_DEVICE`, restart unless stopped. Client `pymilvus` 2.5 to 3.0.2.
Why: The official file is the combination Milvus tests and releases. The app's ORM calls (`Collection`, `utility`) still work in pymilvus 3.0 (deprecated, removed in 3.1).
Trade-off:
- Milvus does not upgrade 2.5 data to 3.0 directly. A site with data must go 2.5 → 2.6.x (latest 2.6 tag) → 3.0.5, one restart each, after backing up etcd and MinIO (`milvus-backup`). Or rebuild the collections from the embeddings, which the nightly updater does from the dataset.
- On this laptop, Milvus 3.0.5 first started on the 2.5.1 data and the older Milvus-tested MinIO crash-looped on data written by the newer `pgsty/minio`. The 2.5.1 test data (64 MB) was moved to `/usr/local/database/milvus-2.5.1-backup` in the Docker VM and 3.0.5 started fresh.
- The ORM API must move to `MilvusClient` before pymilvus 3.1.
Revisit if: pymilvus 3.1 is needed (port the ORM calls first), or a site holds vectors that cannot be rebuilt from images (rehearse the 2.6 step on a copy).

## D-023: App images to Python 3.14 with current libraries (supersedes D-002)
Date: 2026-10-30   Model: Claude Opus 5.5
Context: The owner asked for the app base image to move from Python 3.11 to 3.14. The old pins (numpy 1.24, matplotlib 3.7, opencv 4.10) have no 3.14 wheels, so they move too.
Options:

1. stay on 3.11
2. 3.14 keeping OpenCV on 4.14
3. 3.14 with OpenCV 5.0

Chosen: 3. `python:3.14-slim-trixie`, pinned by digest, in all 8 Dockerfiles. numpy 2.5.4, opencv-python 5.0.0.93, fastapi 0.162.0 (starlette 1.10.0), uvicorn 0.54.0, pydantic 2.14.2, matplotlib 3.11.2, requests 2.34.2, msgpack 1.2.4, ujson 6.0.0, apscheduler 3.11.3, python-dotenv 1.2.4, python-multipart 0.0.32, typing-extensions 4.16.0, flask 3.1.3. `src/main.py` calls `multiprocessing.set_start_method("fork")`: 3.14 defaults to forkserver on Linux, and the workers receive live pymilvus `Collection` objects that would otherwise have to be pickled.
Why: These are the latest stable releases. Compatibility was checked before changing code: ruff `NPY201` found nothing for NumPy 2; all 46 `cv2` names the code uses exist in OpenCV 5.0; `pip check` is clean on 3.14.10; `@app.on_event` still works.
Trade-off: Two major versions moved at once (NumPy 2, OpenCV 5) and the end-to-end recognition path has no real data yet, so numeric behavior of image code is verified only by those checks, CI smoke tests and the deployed stack starting. `@app.on_event` is deprecated and should move to lifespan handlers. Fork after gRPC setup is unchanged from before and stays a known risk.
Revisit if: recognition results shift once real data is loaded, or a library drops `on_event`.

## D-024: Kafka-WebApp as a submodule of the owner's repository
Date: 2026-10-30   Model: Claude Opus 5.5
Context: `.gitmodules` named `gi-hamza-eatai241/Kafka-WebApp` over SSH, but no submodule commit was ever recorded, so nothing was checked out and CI never saw it. Copies also exist at `GIV-AI/Kafka-WebApp`. The owner first chose to absorb it as a folder, to avoid pushing to the GIV-AI organization's repository, then created `hamza-aziz-ai/Kafka-WebApp` (same commit, `4578453`) and chose a submodule pointing there.
Options:

1. plain folder in this repository, sharing its version
2. submodule of `hamza-aziz-ai/Kafka-WebApp`

Chosen: 2, over HTTPS so CI and the deployment clone need no SSH key. Its Dockerfile, CI and releases live in its own repository; Dependabot's `gitsubmodule` updates bump the pinned commit here through the usual CI, auto-merge and release path.
Why: The display client has its own release cycle and also runs on Raspberry Pis, independent of this stack.
Trade-off: Clones need `--recurse-submodules`. A change to the client takes two steps: a release there, then a pin update here. The other two copies are not kept in step.
Revisit if: the planned merge with PTZ-Camera-Classroom-Attendance-System changes how the display client is shared.

## D-025: Green CI is the merge and ship gate
Date: 2026-10-30   Model: Claude Opus 5.5
Context: The Defend What You Ship guide asks a human to read every diff and run a pre-ship gate. Auto-merge (D-013) ships on green CI with no human review, in this repository and in Kafka-WebApp.
Options:

1. human approval on every PR
2. human approval on `feat:` and `fix:` only
3. green CI is the gate

Chosen: 3, the owner's decision: "As soon as the CI checks pass, I am okay."
Why: CI/CD exists to automate this; the owner does not want a manual step in it.
Trade-off: Anything CI does not check ships unchecked, and CI has no test of recognition itself. Anything that must hold has to become a CI check.
Revisit if: a release that passed CI harms a real site.

## D-026: Fresh datasets, with checked enrolment from five or ten photos
Date: 2026-10-30   Model: Claude Opus 5.5
Context: The original datasets (22.5 GB and 1.6 GB) stayed with the owner's previous employer on a Google Drive the owner cannot reach, and no copy exists on this machine. The `.dvc` files pointed at data nobody could pull. The owner's plan is 5 photos per person (front, chin up, chin down, 30 degrees left, 30 degrees right), and 10 for someone who wears spectacles.
Options:

1. keep the old `.dvc` pointers and wait for the data
2. restart the datasets with the owner's photo plan
3. use the interactive group scripts for everyone

Chosen: 2. `src/util/enrol_person.py` enrols one person from `<person_id>/<pose>.jpg`, after `src/util/enrolment_checks.py` passes: the full set is present; each photo has exactly one face, confidence of at least 0.7 (`ENROLMENT_MIN_CONFIDENCE`) and pupils at least 28 px apart; each matches the person's other photos; none matches someone else already enrolled; and the ID is not enrolled yet. Any failure rejects the whole person. Sharpness is shown, not enforced. The `.dvc` files and the manifest now point at the new data; the old hashes stay in git history.
Why: Measured on the owner's 10 photos: all 45 pairs scored 0.78 to 0.94 against a 0.5 threshold, the closest of 30 strangers scored 0.23, and all 10 were still detected and matched at 20 px between the pupils. The checks reject real failures: a missing pose, a photo of someone else (-0.07), and a photo with two faces. LFW showed why one face per photo matters: 150 photos produced 174 vectors, because the old script enrols every face.
Trade-off:
- Downscaled clean photos are the best case. Real CCTV is overhead, compressed and in motion, and is not tested.
- The 0.7 confidence value is a judgment: the owner's photos scored 0.83 to 0.90.
- Spectacles added little in this test: same-pose pairs across the two sets scored 0.86 to 0.92. They stay for glare, which this test cannot show.
- Consent is not enforced by code.
- `enrol_person.py` writes vectors straight to Milvus, so they are rebuilt from the photos rather than versioned.
Revisit if: a real camera test shows missed matches (add overhead photos, or tune the threshold), or a person needs deleting (no deletion path yet).

## D-027: One generic deployment, with no client names
Date: 2026-10-31   Model: Claude Opus 5.5
Context: The code named two former clients through an `INSTITUTE` setting that was built into folder, database and Milvus names, and the enrolment scripts had menus for their groups. The owner wants the project generalized, and will decide later how to serve several clients: one central service or dedicated deployments.
Options:

1. rename `INSTITUTE` to a generic tenant setting
2. remove it, one deployment with fixed generic names

Chosen: 2. `INSTITUTE` and its host-IP settings are gone. Names are `FACE_DATA_COLLECTION_FOR_COSINE`, `FACE_DATA_STAGING_COLLECTION_FOR_COSINE`, `Face_Recognition_Database`, `CCTV_Camera_Surveillance`, and the data folders have no client level. The camera config is `src/Camera-Configuration/camera_configuration.json`. The group menus became plain arguments.
Why: A tenant setting now would guess at a design the owner has not chosen. A dedicated deployment needs none, and a central service needs more than a name prefix.
Trade-off: Breaking: a site with data must rename its Milvus collections, Postgres databases and folders, or re-enrol. The names remain in git history.
Revisit if: the multi-client model is decided.


## D-028: Kafka topics are kept, on a broker volume
Date: 2026-10-31   Model: Claude Opus 5.5
Context: Each `producer-consumer` start and stop deleted and recreated its topics, then slept 30 s. Broker data lived in `/tmp`, so recreating the broker lost every topic. Auto-creation then rebuilt Schema Registry's and Connect's topics with the delete policy (both crash-looped) and the app topics with 1 partition instead of one per camera. The display must stay real-time.
Options:

1. keep deleting topics
2. keep topics, create only missing ones and add partitions for new cameras

Chosen: 2. `ensure_kafka_topics()` creates missing topics and grows partitions, and waits for the result. The broker keeps its data on the `kafka-data` volume and has auto-creation off. Connect gets `CONNECT_REST_PORT` so its health check passes.
Why: Deleting topics lost messages and raced the feedback controller. Kafka-WebApp reads from the end, so old messages are never replayed; the 5 s retention removes them.
Trade-off: Partitions cannot shrink, so removing cameras leaves unused partitions. A topic the producer does not create is refused instead of auto-created.
Revisit if: topic settings must change (alter them with `kafka-configs`, or delete the topic once by hand).

## D-029: Unattended merge and release recover on their own
Date: 2026-10-31   Model: Claude Opus 5.5
Context: PR #41 passed all checks but stayed open: four automerge sweeps logged "no successful ci" and the cause could not be found from those logs. The release run for #40 then failed to create its tag (HTTP 403), because #41 had changed a workflow file on main while it ran. Both needed a person.
Options:

1. leave both to the owner
2. an hourly cron sweep of automerge, and a release retry
3. log what automerge saw; let the watcher start automerge for green PRs left open; hand a stale release run over to a release of main

Chosen: 3. Automerge prints the checks it saw on every skip. Every 10 minutes the watcher starts automerge if a non-draft, non-conflicting PR passed all its checks over 15 minutes ago. When tagging fails and main has moved on, the release run starts a release of main, which holds the same commit, and stops without publishing.
Why: A cron sweep uses Actions minutes every hour even when nothing waits; the watcher already polls GitHub. The newer main always contains the stale commit, so releasing it loses nothing.
Trade-off: The watcher's nudge only runs while the deployment host is on. The 403 cause is inferred from timing, not documented by GitHub; if tagging fails with main unchanged, the run still fails and opens an issue.
Revisit if: the skip log shows why #41 was missed (fix that instead), or a release fails with main unchanged.

## D-030: Face vectors saved with the photos, and Milvus served through an alias
Date: 2026-10-31   Model: Claude Opus 5.5
Context: Enrolment wrote vectors straight into the primary Milvus collection, so a bad update could not be undone and no dataset version said which vectors were being served. `docs/features/dataset-versioning.md` proposed Parquet files outside the dataset and a new alias name. A probe on Milvus 3.0.5 showed that rows sharing a primary key (a person's photos all share `name_id`) are all searchable, but `query` returns one row per key, so vectors cannot be exported back out of Milvus.
Options:

1. Parquet outside the dataset, named by dataset version, model and settings, behind a new alias `FACES_ACTIVE`
2. a `vectors.parquet` in each person's folder, versioned by the existing `FACIAL-RECOGNITION-DATASET.dvc`, and numbered collections behind an alias with the name the app already uses

Chosen: 2. `src/util/face_vectors.py publish` builds `FACE_DATA_COLLECTION_FOR_COSINE_v<n>` from every `vectors.parquet`, loads it, points the alias `FACE_DATA_COLLECTION_FOR_COSINE` at it and releases the previous version; the three newest versions are kept. `use <n>` points the alias back. `enrol_person.py` and `upload_embeddings.py` save the files, then publish. `migrate`, run once by the owner, takes the vectors again from the photos, renames the live collection to `_v0` and creates the alias. New dependency: `pyarrow` 26.0.
Why: Nothing in the app changes: the consumer keeps the same name, and a running `Collection` follows an alias switch without a restart (tested). One `.dvc` file means a dataset version cannot pair photos with the wrong vectors.
Trade-off: Every enrolment rebuilds the whole collection, which is fine for thousands of people and slow for millions. `pyarrow` makes the producer image larger. The nightly updater still writes only to the staging collection, which is not versioned. The files hold no model or settings lineage, and the manifest does not record them yet. A version drops out of Milvus after three newer ones; rebuilding it means checking out that dataset version and publishing again.
Revisit if: enrolments get slow (append to a copy of the current version instead), or the embedding model changes (record its md5 in the files and the manifest).

## D-031: InsightFace-REST 0.9.5.0 on TensorRT 11
Date: 2026-10-31   Model: Claude Opus 5.5
Context: The vendored InsightFace-REST was 0.9.0.0 on the TensorRT 22.10 image (TensorRT 8.5, Python 3.8, 16.3 GB). The owner asked for the latest upstream on the TensorRT image that matches the host's CUDA toolkit 13.3. A first trial (2026-10-30) stopped at worker boot: PyTurboJPEG 2.x needs libjpeg-turbo 3, and Ubuntu 24.04 ships 2.1.5.
Options:

1. stay on 0.9.0.0 with TensorRT 8.5
2. 0.9.5.0 on TensorRT 26.07, installing libjpeg-turbo 3 from its own release
3. 0.9.5.0 on TensorRT 26.07, pinning PyTurboJPEG 1.8.3, which works with Ubuntu's libjpeg-turbo

Chosen: 3. `src/api_trt` is replaced by upstream `if_rest` at `fb854d8`, on `nvcr.io/nvidia/tensorrt:26.07-py3` pinned by digest (TensorRT 11.1, CUDA 13.3, Python 3.12). Local changes: the engine build uses a strongly typed network with FP16 weights from `onnxconverter-common` (TensorRT 11 removed the FP16 flag), engine files carry the TensorRT version in their name, engines are written atomically, `np_apply_along_axis` is no longer numba-cached (numba 0.66 cannot pickle it, so every request failed), and `tostring()` became `tobytes()` for NumPy 2. Added 2026-11-06: the TensorRT backend's ArcFace swaps BGR to RGB by default (`swapRB=True`), as the ONNX and Triton backends do; it had fed `w600k_r50` BGR although the model was trained on RGB (found by the Jetson session against OpenCV's FP32 run: cosine 1.0000 to BGR, 0.9349 to RGB). On the owner's 10 photos, leave-one-out cosine rose from 0.875–0.937 to 0.901–0.944 and the stored camera frame from 0.752 to 0.778, while 119 other faces stayed at 0.191 or below. `/extract` also no longer fails with no `Accept` header.
Why: The service only calls `TurboJPEG()` and `decode()`, which PyTurboJPEG 1.8.3 has; building libjpeg-turbo adds a build step to own. Measured against the running 0.9.0.0 on 330 LFW photos of 30 people (150 enrolled, 180 tested, threshold 0.5): both 173 correct, 0 wrong, 7 below threshold; the same photo's embeddings agree at cosine 0.9951 or more (mean 0.9993). The app's own `IFRClient` gets the same response fields, with msgpack and JSON. The image is 7.1 GB instead of 16.3 GB.
Trade-off: Python packages other than PyTurboJPEG are unpinned, as upstream has them, so a rebuild can pull newer versions. The first start builds new engines (the recognition engine took 50 s here). The CPU image was updated but not built or tested.
Revisit if: Ubuntu ships libjpeg-turbo 3 (drop the pin), or a rebuild breaks on a new package version (pin the versions that work).

## D-032: Generic GPU defaults instead of the A100 MIG layout
Date: 2026-10-31   Model: Claude Opus 5.5
Context: `standalone-services.env` described the original A100 host: MIG slices `7:0` to `7:4`, two workers per container and batch sizes 64 and 128. Every other host needed a profile (D-015). On 2026-10-31 a start without `HOST_PROFILE` used those defaults here: InsightFace failed with `unknown device` and Milvus was left created but not running. The owner asked for generic defaults.
Options:

1. keep the A100 defaults and a profile per host
2. generic defaults that fit one small GPU, and a profile only where a host needs more

Chosen: 2. Every GPU service defaults to GPU 0. InsightFace runs one container there, with one worker and batch sizes 8 and 16; the owner judged this laptop too small for two. nginx stays on port 6385 with that one backend, so the app is unchanged. `MIG_GPU` is renamed `INSIGHTFACE_GPUS`, and the containers `insightface-rest-trt-0` and `-1`. The `laptop-rtx4050` profile equaled the new defaults and is removed. `start_standalone_services.sh` now reads `HOST_PROFILE` from `.env`.
Why: The defaults run on any host with one NVIDIA GPU, including this laptop, where the same values ran 0.9.5. A large host still gets its own values through a profile.
Trade-off: A large GPU is under-used until its profile raises the batch sizes. MIG layouts are still possible, but only through a profile. More InsightFace containers start, but nginx does not balance across them yet.
Revisit if: a second deployment host exists (give it a profile), or throughput needs more than one InsightFace container (design load balancing that follows `INSIGHTFACE_GPUS`).

## D-033: Deployment hosts get images and a source-free bundle, not the repository
Date: 2026-10-31   Model: Claude Opus 5.5 with Codex GPT-6.1 Sol (council)
Context: Deployment hosts will be client machines. Today a host holds a full clone of this repository with its history, the producer container mounts that clone, InsightFace-REST is built on the host from source and runs with the source mounted, and the watcher uses the owner's `gh` login. The owner wants client hosts to hold configuration, environment and client data, but not our code.
Options:

1. keep the clone, and restrict who can log in to the host
2. ship images plus a source-free deployment bundle from the registry, with a pull-only credential
3. run the logic on our own servers, so clients hold no logic at all

Chosen: 2, in three PRs. This one: the producer mounts only `master.env`, the camera config, logs and frames; CI builds the InsightFace-REST image once per source tree (`insightface-image.yml`, tagged `<version>-<git tree of src>`) and hosts pull it with no source mount; each release publishes `cctv-face-recognition-deploy:<tag>`, a scratch image with an allow-list of compose files, ops scripts, templates and licences (`deploy/make_bundle.py`), every image pinned by digest and a `release-manifest.json`; `:stable` moves to it only after the release is published, and never back. Next: the watcher pulls `deploy:stable` instead of using git and `gh`, with no self-update; then a package-only machine account and the switch of this host.
Why: It removes the clone, its history and the owner's credentials from hosts with the tools already in use (GHCR, Docker). Digests, not tags, because the v2.0.2 tags were pushed twice.
Trade-off: Not 3: the images still hold readable Python, which a host administrator can copy out until the images are compiled (step 4), and compiled code is still our logic on their machine. The bundle's compose files and ops scripts are ours too; the owner accepts them on client hosts. The InsightFace pretrained models are for non-commercial research per the InsightFace README: rights must be settled before a paid client deployment. Client biometric data must stay out of this repository; a dataset store on the same host is not a backup.
Revisit if: the watcher and credential PRs land (record them here), compiled images exist (new package names, so client tokens cannot pull the old Python images), or a client needs the logic off their premises (option 3).

## D-034: The watcher deploys bundles from the registry, with no git and no GitHub login
Date: 2026-10-31   Model: Claude Opus 5.5 with Codex GPT-6.1 Sol (council)
Context: Second step of D-033. `deploy/watch.py` found releases with `gh release list`, fetched with the owner's `gh` login and deployed with `git checkout` in a full clone; it also nudged automerge with `gh`. Client hosts must have neither the repository nor that login.
Options:

1. a GitHub Release asset per release (needs a GitHub API token on the host)
2. a containerised watcher with the Docker socket
3. the host watcher pulls the bundle image's `:stable` tag with the registry login it already needs for the app images

Chosen: 3. The watcher reads the release from the bundle's version label, copies the bundle out with `docker create` and `docker cp` without running it, refuses it unless `release-manifest.json` is for that release and pins only our images by digest, stages it atomically in `releases/<tag>`, and runs compose from it with `-p cctv --project-directory site`. Smoke test, 90-second stability check, rollback, failed-release suppression and the stopped-stack rule are kept. The watcher never updates itself: the owner installs `watch.py` from a bundle. A registry or site-config problem stops deploys with one notification, not one every poll. The automerge nudge moved to `deploy/nudge_automerge.py`, scheduled only on the owner's laptop.
Why: One credential, for the registry, serves both the images and the bundle; no API token and no socket mount. Option 2 needs bind sources as host paths from inside a container, which is fragile on Docker Desktop. A watcher that replaced itself could disable every later deploy and rollback.
Trade-off: Python 3 is needed on the host. Trust moved from "the tag is on main" to "only release.yml can move :stable", which holds while only the workflow and the owner can write the packages. The standalone services' scripts still assume the repository layout; switching this host (next PR) has to account for that. Until then, on this host: once the old watcher deploys a release with this change, its checkout replaces the scheduled watch.py with this one, which finds no site folder and stops deploying with one message, so the switch should follow straight after.
Revisit if: a host cannot have Python, or watcher updates become frequent enough to need a safe self-update (previous version kept, atomic switch, recovery tests).
## D-035: The ROI page draws polygons into the camera configuration
Date: 2026-10-31   Model: Claude Opus 5.5
Context: `Custom-ROI-Provisioning/app.py` could not start: it imported `IP_CAMS`, `create_mask` and `roi_coordinates`, which no longer exist, and it saved a rectangle by rewriting `src/parameters.py` inside the image. The producer has since moved to per-camera polygons in `camera_configuration.json` (`masking-coordinates`, applied by `crop_and_mask_roi` to the full-resolution frame). The owner chose repair over deletion.
Options:

1. delete the page and keep only the desktop tool `crop_rectangle.py`
2. repair the rectangle page against `parameters.py`
3. rebuild the page around the camera configuration: polygon on a full-resolution snapshot, saved into `masking-coordinates`

Chosen: 3. The page lists the cameras from the configuration, opens each one with `camera_stream_url` (now shared with the producer, so both connect the same way), shows a full-resolution snapshot, takes clicked points, previews with the producer's `crop_and_mask_roi`, and saves into that camera's `masking-coordinates` with validation and an atomic write. It runs as `roi-provisioning` behind the compose profile `roi`: off by default, on 127.0.0.1 only, with the camera configuration mounted read-write for this service only. Releases build and pin its image with the others.
Why: The configuration is already the one place the producer reads regions from, so the page writes exactly what is used; editing source files from a container cannot work with images (D-001) and breaks with compiled code (step 4).
Trade-off: The producer reads regions at start, so a saved region applies after a restart of `producer-consumer`. No login: anyone on the host can change regions while the page runs. The desktop tool stays for use without Docker.
Revisit if: regions must apply without a restart, or the page must be reachable from another machine (add a login first).
Added 2026-11-06 (council with Codex): the page saves the size of the snapshot the region was drawn on as `masking-frame-size`, only if a fresh frame still has it (409 otherwise), and the producer refuses the region when the camera's frames have another size. Scaling the points or storing 0..1 coordinates was rejected: a camera's lower-resolution modes often crop the picture, so either would be silently wrong. Older regions without a size keep working on bounds alone. Re-aiming at the same resolution is still not detected.
## D-036: Client separation: shared infrastructure, one app stack per client, local logins
Date: 2026-10-31   Model: Claude Opus 5.5 with Codex GPT-6.1 Sol (council)
Context: One codebase must serve a dedicated deployment on a client's own host and a central deployment for several clients on ours, with a standard tier and an optional DeepStream tier (owner, 2026-10-31). Today everything is single-site: fixed container names, host ports and compose project; one Postgres role for all services; Milvus with its default root login; Kafka without authentication; one shared API key in the URL; display and collector endpoints with no login; databases and Kafka topics created at runtime by the app. This host has one 6 GB GPU. This is a rehearsal; nothing is sold.
Options:

1. separate everything per client, including InsightFace and Milvus
2. share the infrastructure and run a separate app stack per client
3. one app process serving all clients, with a tenant ID on every query

Chosen: 2. Shared per host: InsightFace (stateless, the GPU), Milvus, Postgres, Kafka, the MinIO dataset store. Per client: an app stack from the same images and bundle, its own site folder (configuration, logs, photos, vectors), and inside the shared servers its own Milvus database and login (collection names inside unchanged, D-030 alias included), its own Postgres databases and a role that reaches nothing else, its own Kafka topic and consumer-group prefix enforced by SCRAM logins and deny-by-default ACLs, its own MinIO bucket and access key. A dedicated deployment is the infrastructure plus one client stack.
- Identity: a required, immutable, validated `CLIENT_ID` per stack; missing configuration fails, never falls back; today's names survive only through an explicit mapping for the owner's site.
- Provisioning: a provisioning command with admin credentials that never enter app containers creates databases, logins, grants, buckets, topics and partitions; the app only checks they exist at start and fails clearly if not. Exception: the face-vector publisher (D-030) may create numbered collections and switch the alias inside its own Milvus database only.
- Logins: local accounts per client in its Postgres; roles `client_admin`, `enrolment_operator`, `viewer`. Passwords hashed with stdlib `hashlib.scrypt` (OWASP parameters, explicit `maxmem`, unique salts, constant-time comparison). Random session tokens stored only as hashes; secure host-only cookies over HTTPS, CSRF protection, expiry, revocation, login throttling, bounded password length. Machines (ERP pulls, collector, displays, Kafka-WebApp) get scoped tokens; the shared API key leaves the URL. Owner support uses explicit per-client accounts; no login bypasses clients.
- Tiers: central clients' tier is owner-set configuration the client cannot edit, checked server-side, selecting exactly one recognition image; bundles reference only enabled images. Dedicated clients are gated by which packages their pull token can download, which cannot revoke an image already on their host.
- Biometric data: each client's photos and vectors stay in its folders and bucket, never in our repository, CI or images. Each Milvus version records the dataset snapshot it was built from; bucket versioning alone is neither a snapshot nor a backup. The owner's own test photos stay as DVC data for development only.
Why: settings are global per process today, so a process serving one client needs no tenant filtering, and it fits one GPU. Option 3 needs a tenant filter on every query, queue and cache, where one miss exposes another client's biometric data; option 1 does not fit a 6 GB GPU.
Trade-off: clients still share administrators, failures and GPU capacity; separation is enforced by permissions, not hardware, with no performance guarantee. Unproven until steps 3 and 5: Milvus per-database permission enforcement in practice, and how many clients one shared GPU carries.
Plan, five PRs, each with its tests:

1. names and configuration: required `CLIENT_ID`, owner mapping, per-client databases, topics and consumer groups (missing or invalid configuration refused; identical camera or person IDs in two clients never collide)
2. deployment layout: no fixed container names, separate compose projects, per-client data and log folders, networks, watcher state and locks, image cleanup that keeps every client's rollback images or none on central hosts (A's stop, upgrade or rollback leaves B running with its rollback images)
3. provisioning and credentials: restricted logins in Postgres, Milvus, Kafka, MinIO, publisher exception (A's credentials refused on all four for B's data; publishing succeeds with client-only credentials)
4. accounts and protected callers: HTTPS hostnames per client behind a reverse proxy (secure cookies need it), logins, roles, sessions, machine tokens, protection on the API, feedback intake and Kafka-WebApp pages and WebSockets (role matrix, cross-client sessions, login bypass, CSRF, throttling, revocation)
5. tiers and recovery: tier selection, then a two-client synthetic rehearsal: snapshot, publish, restore one client without touching the other, remove a client

Enrolment (8c), the live view (8b), the Android app (8d) and deletion (8e) build on these boundaries.
Revisit if: a real client is signed. Then also: model licences; DPDP Act lawful basis, notices, retention and erasure, breach notification, children's data and a processor agreement for central mode; an audit log of views, enrolments and deletions; off-host backups with restore tests; encryption between hosts; credential rotation; MFA or SSO through OIDC where required.

## D-037: Per-client logins on the shared services, and how they are switched on
Date: 2026-10-31   Model: Claude Opus 5.5 with Codex GPT-6.1 Sol (council)
Context: D-036 step 3 gives each client logins that reach only its own data in PostgreSQL, Milvus, Kafka and the MinIO dataset store. Today the app uses the PostgreSQL superuser, Milvus has no authentication (`root:Milvus` in the code), Kafka is PLAINTEXT on 9092 for app producers and displays, and the dataset store has only its root login. D-036 left one point unproven: whether Milvus enforces per-database permissions. Throwaway spikes on 2026-10-31 showed it does on 3.0.5: a user granted the privilege groups `DatabaseReadWrite`, `DatabaseAdmin` and `CollectionAdmin` on its own database could create, insert, alias, query and drop there. The same user was refused on other databases and on admin actions. Kafka SCRAM users with prefixed ACLs were likewise confined to their own topics and groups.
Options:

1. one admin login per service, shared by every client stack, with isolation by names only
2. per-client logins created at runtime by the app
3. per-client logins created by a provisioning command that holds the admin rights; the app only uses its own

Chosen: 3.
- Provisioning: `deploy/provision.py` runs on the host.
  - Clients: it creates, for each one, a Postgres role owning the client's two databases, with `CONNECT` revoked from `PUBLIC`. It also creates a Milvus user and role over the client's database only, Kafka users `<c>_app` (Write and Describe) and `<c>_display` (Read on topics and groups) on the prefix `<c>.`, and a MinIO bucket `<c>-enrolment` with an access key whose policy covers that bucket only.
  - Passwords: they are generated once and saved atomically to the client's site `.env` before any service is touched, and reruns reuse them. An account whose password is no longer saved stops provisioning instead of being reset.
  - Milvus root: `--init-milvus-root` replaces root's default password, saving the new one first.
- Shared settings: the Kafka listener and authorizer settings and the Milvus `user.yaml` live in `STANDALONE-SERVICES/auth/`. The production compose files and `deploy/test_isolation.py` both read them.
- Kafka: the plaintext listeners (inter-broker, controller) bind to the broker's loopback. `User:ANONYMOUS` is the superuser on every listener, but only tools inside the broker container reach those listeners. All other traffic uses SCRAM on 9092.
- Kafka add-ons: Schema Registry, Connect, ksqlDB, REST Proxy and Flink go at the cutover. REST Proxy and Connect were published, unauthenticated routes through the internal listener to every topic, and the app uses none of them.
- Owner topics: the owner's topics become `owner.*` at the cutover, so every client is covered by the same prefix rules. Owner database and collection names stay.
- Rollout in three PRs:
  1. 3a: provisioning and the isolation test, with no runtime effect.
  2. 3b: the app and Kafka-WebApp use the per-client logins and stop creating databases and topics themselves. `LEGACY_SHARED_SERVICES=1` keeps the owner on today's behaviour until the cutover, honoured only with `CLIENT_ID=owner`. The watcher is paused before 3b merges.
  3. 3c: a manual cutover. Turn on auth, move the owner's app tables, partitions and sequences to `owner_app` one by one (never `REASSIGN OWNED`, which also moves databases and tablespaces), switch the producers and displays together, deploy, verify, then resume the watcher.

Why: only option 3 keeps admin rights out of every client stack, so a stack, or anyone holding its `.env`, cannot reach another client's data; option 1 relies on names, which nothing enforces. Option 2 needs admin rights in the app. Generating the passwords before touching any service, and refusing to reset an unknown one, makes a failed or interrupted run safe to repeat.
Trade-off:
- Kafka encryption: SASL_PLAINTEXT authenticates but does not encrypt.
- Passwords in argv: they appear briefly on command lines inside the Kafka and MinIO containers.
- Provisioning is per host, by hand.
- The CPU Milvus in the test proves authorisation only, not GPU indexes.
- After the cutover, releases before 3b are no longer valid rollback targets.
Revisit if: real client traffic crosses networks (SASL_SSL and TLS for Postgres and Milvus), anything other than the broker must reach its plaintext listeners (named SCRAM admin instead of ANONYMOUS), or individual displays must be revoked (one Kafka login per display).

## D-038: Stateful services use named volumes
Date: 2026-11-01   Model: Claude Opus 5.5
Context: Postgres and Milvus (with its etcd and MinIO) used bind mounts to Linux paths. On Docker Desktop those paths are inside the VM and are emptied by a restart, which lost their data on 2026-11-01 (docs/bugs/2026-11-01-data-lost-on-restart.md). The owner directed mounted volumes for persistent storage.
Options:

1. keep the Linux paths, and run a restore after every restart
2. bind mount Windows folders
3. named Docker volumes

Chosen: 3. PostgreSQL uses `cctv-postgres-data`; Milvus uses `milvus-data`, `milvus-etcd` and `milvus-minio`. Each has an explicit `name`, so the data stays with the service if its compose project changes (#62 moves PostgreSQL to a shared service). `DOCKER_VOLUME_DIRECTORY` is removed.
Why: named volumes work the same on Docker Desktop and Linux and persist on Docker's own disk; Kafka's named volume survived this same restart (D-028). Option 2 depends on the host's folder layout, and POSIX ownership and fsync behave poorly on Windows mounts, which databases rely on.
Trade-off: the data is inside Docker's disk, so copying it needs `docker run` or `pg_dump`, not a file manager, and removing Docker Desktop's data or running `docker volume prune` deletes it. Off-host backups are still missing (D-036).
Revisit if: a host needs its data on a specific disk (a bind mount or a volume driver).

## D-039: Accounts live in the API, in each client's database
Date: 2026-11-01   Model: Claude Opus 5.5
Context: D-036 step 4 needs logins, roles, sessions and machine tokens per client, with the shared API key out of the URL. It does not say where they run.
Options:

1. a new authentication service per client
2. a hosted or open-source identity provider
3. inside the existing API service, in the client's own database

Chosen: 3, built in `src/api/accounts.py`. Tables `accounts`, `sessions`, `machine_tokens` and `login_failures` sit in the client's database, so an account cannot reach another client. The roles, `hashlib.scrypt` passwords, hashed session tokens, `__Host-` cookies, CSRF tokens, 8-hour expiry and throttling follow D-036. Throttling is 5 failures in 15 minutes per name. `GET /auth/check` lets the reverse proxy of the next PR guard pages that have no login of their own, such as Kafka-WebApp and its WebSockets, with no change to them.
Why: no new image, service or dependency, and the API already has a connection pool and FastAPI. Sensitive pages are few, so a small module is enough.
Trade-off: throttling by name lets someone lock a known name out for 15 minutes. `/docs` stays open until the proxy can close it, and the watcher's smoke test uses it. Until the proxy arrives the API is plain HTTP, so the cookie works only on localhost, and credentials and tokens cross the LAN in clear. Accounts are managed by command line; there is no admin page yet.
Revisit if: a client needs single sign-on, or enrolment (8c) needs per-person permissions.

## D-040: One Caddy per host in front of every client stack
Date: 2026-11-01   Model: Claude Opus 5.5
Context: D-036 step 4 puts HTTPS per client behind a reverse proxy, because secure cookies need it. Kafka-WebApp's pages and WebSockets have no login of their own, and it lives in another repository.
Options:

1. one proxy per client stack: each needs its own public port
2. nginx: certificates and auth requests need more configuration and tooling
3. one Caddy per host, with a private CA and a route file per client

Chosen: 3. `STANDALONE-SERVICES/Proxy` publishes only 443 and keeps its CA in the named volume `cctv-proxy-data`. `deploy/provision.py` writes each client's route to the deploy folder's `proxy` folder, away from `sites`, which holds secrets. The proxy reaches stacks over the shared network `cctv-edge`, by the container names compose derives from the project. Pages go through the API's `/auth/check` with `forward_auth`, so Kafka-WebApp needs no change and its WebSockets are guarded too. `/api/*` goes to the API with its docs closed, and `/auth/*` carries the sign-in page. A client's host name is `SITE_HOST` in its site `.env`, by default `<client>.localhost`.
Why: Caddy issues and renews its own certificates, and `forward_auth` guards a page without touching the app behind it. The API, display and portrait ports stay on 127.0.0.1, because the watcher's smoke test and port checks use them.
Trade-off: each device must trust the private CA once. Someone with a login on the host can reach those ports without a session, the same as Kafbat. A proxy outage takes every client on the host offline. Raspberry Pi displays are not covered yet: they read portraits from port 20013, which no longer reaches the LAN. There is no sign-out button on the display yet, only 8-hour expiry and revocation by command.
Revisit if: a client needs a public certificate, or Pi displays return.

## D-041: A client's tier is an owner-set file on the host
Date: 2026-11-02   Model: Claude Opus 5.5
Context: D-036 step 5 needs a tier per client that the client cannot edit, selecting exactly one recognition image. Only the standard tier has an image today; DeepStream is a later roadmap item.
Options:

1. a key in the site's `.env` or `master.env`
2. a `tier` file in the site folder, checked by the watcher against the tiers the release lists
3. compose profiles for each tier now, before a second image exists

Chosen: 2. `sites/<client>/tier` holds one word, and no file means `standard`. `make_bundle.py` lists the release's tiers in `release-manifest.json`, and `deploy()` in `watch.py` refuses a tier the release does not list, which rolls that client back and notifies. Choosing the image is added with the first paid image, as there is only one to choose today.
Why: `master.env` is mounted into containers, and `.env` holds credentials that only provisioning should write. No container mounts the site's `tier` file, so on a central host a client has no way to edit it. The missing-file default gives the cheapest tier, so a mistake never grants a paid feature.
Trade-off: this only guards central hosts, and dedicated clients stay gated by which packages their pull token can read, which cannot take back an image already on their host. A refused tier also marks the release failed for that client, so after fixing the file the owner runs `watch.py --enroll <client>`.
Revisit if: the DeepStream image ships. Then add it to `TIERS` and make the compose file select the image by tier.

## D-042: Per-client snapshot, restore and removal, and removed Kafka logins are disabled, never deleted
Date: 2026-11-02   Model: Claude Opus 5.5
Context: D-036 step 5 needs one client snapshotted, restored and removed without touching another. Milvus cannot export our vectors, because rows share a person's ID as primary key and `query` returns one row per key (D-030). On a throwaway `cp-kafka:8.4.0` broker, `kafka-configs --delete-config SCRAM-SHA-512` for one user left the other logins working until the next restart, when the broker listed no SCRAM users and refused every client. Removing topics and ACLs alone did not do this, and neither did replacing the password. It was repeated on a broker running nothing else.
Options:

1. delete the client's Kafka users, as the other services do
2. disable them: a random password nobody holds, and no ACLs
3. leave the Kafka users as they are

Chosen: 2, in `deploy/recovery.py`.
- `snapshot` writes `sites/<client>/snapshots/<time>`: a `pg_dump` of both databases, the bucket, the site's data folders and a `snapshot.json` of hashes. It holds no passwords.
- `restore` checks the hashes and refuses another client's snapshot or a stack with containers. It replaces the site's data, drops and recreates the two databases, reruns provisioning, restores the dumps and mirrors the bucket, then rebuilds Milvus with the release's `face_vectors.py publish` from the restored `vectors.parquet` files.
- `remove` needs `--confirm <client>`, refuses the owner and a stack with containers, and clears Kafka, Milvus, the store, PostgreSQL and the proxy route. The site folder goes last, because its `.env` lets an interrupted run be repeated.
Why: a client's removal must never reach another client, and one deleted login reaches all of them. Rebuilding Milvus from the files is the existing path (D-030), so there is no second way to fill it.
Trade-off: each removed client leaves two disabled login names on the broker, and its ID cannot be used again there: provisioning stops on it, as it does for any login whose password is not saved. Snapshots sit on the same host, so they are not off-host backups, and `remove` deletes them with the site. `restore` also needs the site's `.env`, which no snapshot holds.
Revisit if: a Kafka upgrade fixes the login deletion. Prove it with a restart on a throwaway broker first. Never run `--delete-config` on a live broker.
Proof on the live host, 2026-11-02: a temporary client `rehearsal` on v2.9.2 was provisioned, given synthetic vectors for 3 people (16 rows) and published. Its snapshot was taken, then its Milvus collections and dataset folder were deleted. `restore` rebuilt Milvus with the release's real `face_vectors.py publish`: 16 rows in use, and a search for one vector of each person returned that person. `remove` then left no site folder and no Milvus database. The owner's Milvus versions, 22 running containers and 0 unhealthy were the same before and after. The ID `rehearsal` is spent on this broker.

## D-043: Edge nodes keep face crops, stored with the client's own data
Date: 2026-11-03   Model: Claude Opus 5.5   Decided by: owner
Context: the dynamic face dataset collector keeps the best `NUMBER_OF_PICTURES` (3) crops of each recognised person per camera cluster, in `DYNAMIC-FACIAL-RECOGNITION-DATASET/<person>/<cluster>/` and the `face_images` table. The nightly updater re-embeds them into the Milvus staging collection, and a score down to 0.45 is accepted when staging also matches (`inference_data_cleaner.py`). A Jetson edge node (roadmap item 12) ran without the collector, so it kept no crops. The Jetson must serve two layouts: everything on the Jetson, or the Jetson as an edge node of a central host.
Options:

1. keep crops: the edge node sends them to the client's collector, which stores them beside that client's PostgreSQL and Milvus
2. send vectors only, no images
3. keep no crops from edge nodes

Chosen: 1. In the Jetson-only layout the collector runs on the Jetson. In the edge layout the producer-consumer posts crops to the central host's collector for that client, never to a store on the edge node.
Why: staging is how recognition follows a person's changing appearance, and edge cameras would otherwise never feed it. Vectors alone cannot be re-embedded when the model changes, and option 3 makes edge cameras recognise worse over time than central ones. One store per client keeps the crops inside snapshot, restore and removal (D-042) and inside a person's deletion, and losing an edge node loses no data.
Trade-off: face images cross the network from the edge node. Over a LAN the volume is small, as only a better crop replaces a kept one. An edge node outside the client's LAN needs the collector behind the proxy with TLS and a per-node token before it is used.
Needed before an edge node keeps crops: a `DYNAMIC_FACE_DATA_COLLECTOR_API` override in `master.env`, as `INSIGHTFACE_HOST` has; camera clusters read from the camera configuration, as `face_saver.py` hardcodes maingate cameras 1 to 10 and raises `KeyError` for any other camera; and the deletion tests (8e) covering crops.
Revisit if: a client forbids face images leaving the edge site. Then use option 1 with the collector, PostgreSQL and Milvus staging on the edge node.

## D-044: GitHub builds arm64 images for the Jetson
Date: 2026-11-03   Model: Claude Opus 5.5
Context: the owner wants GitHub to build the Jetson's images, with both layouts left open: everything on the Jetson, or the Jetson as an edge node of a central host. The app images built unchanged on the Jetson (roadmap item 12). Every third-party image we use already publishes arm64, as does the display image from Kafka-WebApp. InsightFace-REST needs its own Dockerfile there, `Dockerfile_trt_jetson`. GitHub's `ubuntu-24.04-arm` runners are available to private repositories and use the same Actions minutes.
Options:

1. one tag per app image holding both architectures, each built natively on its own runner
2. separate `-arm64` tags and a second compose file for the Jetson
3. cross-build arm64 under QEMU on the amd64 runner

Chosen: 1. The release's own CI run builds and smoke-tests each image on a runner of each architecture and pushes the ones that pass as `<tag>-amd64` and `<tag>-arm64`, then `release.yml` `docker buildx imagetools create` joins them under `<tag>`. Nothing is built twice. The bundle pins that index digest, so each host pulls its own architecture with the same compose file. CI smoke-tests arm64 on a PR only when a Dockerfile, a `requirements.txt`, `ci.yml` or `release.yml` changes, and every release builds and smoke-tests both. InsightFace-REST for the Jetson is a separate tag, `<version>-<tree>-jetson`, built by `insightface-image.yml` on an arm64 runner. It is a different TensorRT and base image, not the same image for another architecture. Superseded by D-046: InsightFace-REST is now one multi-arch image too.
Why: one compose file and one bundle serve both layouts and the x86 host. Native runners avoid QEMU, which is many times slower for builds that install Python wheels.
Trade-off: a release now needs both architectures, so an arm64-only failure blocks an x86 release until fixed. Each release uses about twice the image build minutes. The Jetson InsightFace-REST image is published but not yet in the bundle. The Jetson layouts add it, as they add the edge-node settings of D-043.
Revisit if: arm64 builds break often enough to hold up x86 releases. Then let the arm64 leg fail without blocking, and publish amd64 alone.

## D-045: Camera streams decode on NVDEC through FFmpeg, with OpenCV as the fallback
Date: 2026-11-03   Model: Claude Opus 5.5   Decided by: owner (option 2 on this machine first, CPU fallback kept, option 3 as a toggle)
Context: on the Jetson the producer was CPU-bound (437% CPU for 4 cameras) while the GPU sat at 15 to 56%. On the laptop, reading one 1080p frame the producer's way cost 39 ms of CPU: decoding, scaling, and a darkness check that blurred the full frame. Frames then went to InsightFace-REST as base64 JPEG.
Options:

1. DeepStream for the whole pipeline (roadmap item 11)
2. decode on NVDEC in the producer, through FFmpeg's cuvid decoders in a subprocess per camera, which also scale on the GPU
3. send frames to InsightFace-REST uncompressed instead of as JPEG
4. OpenCV built with CUDA video decoding (`cudacodec`) in the InsightFace-REST image

Chosen: 2, with 3 as a toggle, in `src/util/video_source.py` and `insightface_face_detection.py`. `VIDEO_DECODE=auto` is the default and falls back to OpenCV per connection, and `FRAME_TRANSPORT=jpeg` stays the default (docs/features/gpu-decode.md).
Why: 16 cameras of 1080p30 took 135% CPU at 30 fps on NVDEC, against 1,339% at 25 fps on the CPU. FFmpeg with NVDEC was already in the producer image, and InsightFace-REST already takes msgpack bodies with raw bytes, so neither needed a new dependency or image. Option 4 was rejected because InsightFace-REST never sees video, only still frames. Option 1 stays the larger, later step.
Trade-off: each GPU camera costs about 131 MB of VRAM for its own CUDA context, so the laptop's limit is about 24 cameras. The producer now reserves the GPU, so a host needs an NVIDIA GPU for it, as every host already has for InsightFace-REST. The Jetson's FFmpeg has no NVDEC, so it stays on the CPU until a GStreamer `nvv4l2decoder` path exists. `bmp` measured slower per batch here (119 against 71 ms), so it stays off unless the producer's CPU is the limit.
Revisit if: VRAM per camera limits a client. Then decode several cameras in one process (shared CUDA context) or move to DeepStream.

## D-046: InsightFace-REST on TensorRT 26.03 (TensorRT 10), one image for amd64 and arm64
Date: 2026-11-03   Model: Claude Opus 5.5   Decided by: owner
Context: InsightFace-REST was two images: `tensorrt:26.07-py3` (TensorRT 11.1) for x86 (D-031), and `l4t-tensorrt:r10.3.0` with its own Dockerfile for the Jetson (D-044). DeepStream 9.1, the planned optimised pipeline (roadmap item 11), is built on TensorRT 10.16.0.72 and CUDA 13.2 on x86, and TensorRT 10.16.1.7 on Jetson with JetPack 7.2, per NVIDIA's matrix in the `deepstream-inspect-stack` skill. NVIDIA's `tensorrt:26.03-py3` carries TensorRT 10.16.0.72 and CUDA 13.2 for amd64 and arm64, and its arm64 build runs on the Orin Nano.
Options:

1. `tensorrt:26.03-py3` (TensorRT 10.16) for both architectures, one Dockerfile
2. `tensorrt:26.10-py3` (TensorRT 11.4, CUDA 13.4) for both
3. keep TensorRT 11 on x86 and `l4t-tensorrt` on the Jetson

Chosen: 1. `Dockerfile_trt` is on `26.03-py3` by digest, `Dockerfile_trt_jetson` is deleted, and `insightface-image.yml` builds it natively on an amd64 and an arm64 runner and joins both under one tag. `icc-rt` and `onnx-simplifier` install on x86 only, as neither has an arm64 wheel and `onnx-simplifier` is never imported.
Why: the owner chose TensorRT 10 so the move to DeepStream 9.1 keeps the same TensorRT. One image means one Dockerfile, one tag the laptop and the Jetson both pull, and the bundle pins one digest. On both machines the new image found the same 119 faces as the old one, embeddings within cosine 0.9983, and it answered slightly faster (docs/features/jetson-arm64.md).
Trade-off: the Jetson image grows from 6.18 to 21.5 GB. x86 moves back from TensorRT 11.1 to 10.16, so `onnx_to_trt.py` takes its TensorRT 10 path (FP16 builder flag) on both. Engines are rebuilt once per TensorRT version; their file names carry it, so the old ones stay usable for a rollback. The Jetson's DeepStream 9.1 container is NVIDIA's arm64 release 26.04 with TensorRT 10.16.1.11, one build ahead of 26.03; the owner kept 26.03 on both machines, because a 26.04 image only on the Jetson would split InsightFace into two images again, and InsightFace builds its own engines, so none are shared with DeepStream.
Revisit if: DeepStream moves to TensorRT 11, or the Jetson's disk becomes the limit.

## D-047: Live view through one MediaMTX per client, as HLS behind the existing sign-in
Date: 2026-11-03   Model: Claude Opus 5.5   Decided by: owner (recommended defaults)
Context: roadmap 8b asks for each camera's video passed through, beside its latest recognitions, with no overlays. Browsers cannot play RTSP, and camera logins must stay out of the browser.
Options:

1. delivery: HLS through the existing Caddy route and sign-in, or WebRTC with its own UDP port and auth
2. who watches: all three roles, or `client_admin` and `viewer` only
3. where: one MediaMTX per client stack, or one shared per host like Caddy

Chosen: HLS, `client_admin` and `viewer`, one per client stack (docs/features/live-view.md). The API writes MediaMTX's configuration from the camera configuration at start into a Docker volume; MediaMTX serves HLS only and pulls a camera only while someone watches; the proxy's `/live/*` route checks `/live/check` with `forward_auth`.
Why: HLS needs no new port or auth and passes the existing sign-in. Live video of people is not needed for enrolment work. Per-client MediaMTX keeps each client's camera passwords and streams in its own stack, as D-036 does for data.
Trade-off: measured 3.8 s glass to glass with the owner's phone (0.9 s median of it the phone's RTSP stream over Wi-Fi, up to 2 s), 2.8 s until the player's first stall. The owner sees a similar delay on the recognition display without HLS and attributes it to the RTSP stream; the batch collection was benchmarked by the owner as far smaller. One more container per client. Each client's proxy route must be regenerated after the release that adds it. Containers of other clients on `cctv-edge` can reach MediaMTX directly, as with the display (D-040).
Revisit if: a client needs under about 1.5 s; then tune HLS with our own player or move to WebRTC.

## D-048: Enrolment API in the client's stack, photos in its bucket, checks and publishing in a worker
Date: 2026-11-03   Model: Claude Opus 5.5   Decided by: owner (login and storage), engineering defaults (worker, lock)
Context: roadmap 8c, the server side of the enrolment app's provisional contract (Face-Dataset-Collector FEATURE-001). The app needs a token it can send as a header, durable uploads, per-photo reasons, and one open job per person. Accounts give browsers an HttpOnly cookie with a CSRF token (D-039).
Options:

1. login: the contract's `/auth/login` returning `{token}`, or a separate `/auth/token`
2. photos: the client's MinIO bucket `<client>-enrolment` (D-037), or the site folder as the command line uses
3. checking and publishing: a thread in the API, or a worker of its own

Chosen: `/auth/token` and the bucket (owner), and a worker (docs/features/enrolment-api.md). `/auth/token` opens the same session as the cookie login and returns it for a Bearer header, which `accounts.identify` now accepts. The API stores uploads and job rows; `enrolment-worker` runs on the producer-consumer image, checks with `enrol_person.check_photos`, and publishes under a PostgreSQL advisory lock.
Why: browsers keep a session out of script reach while the app gets a header token. The bucket keeps photos per client, inside snapshot and restore (D-042), and off the host's site folder. The API image has neither the Milvus nor the Parquet library, while the producer-consumer image has them and the InsightFace client, so the worker needs no new image; only `psycopg2-binary` and `minio` were added. Publishing rebuilds the whole collection (D-030), so one at a time.
Trade-off: one more container per client. Every acceptance rebuilds Milvus, about 10 s for one person on the laptop. A rejection names no other person to the operator, only to the server log. Pose and blur limits come from one person's photos and are provisional. The roster is filled by command line until an admin page exists.
Revisit if: enrolments queue behind each other, then publish incrementally instead of rebuilding.

## D-049: Department-scoped matching, and a COSINE or L2 toggle on one collection
Date: 2026-11-03   Model: Claude Opus 5.5   Decided by: owner (department rules, toggle), engineering defaults (where departments live, threshold conversion)
Context: roadmap 8f. In an organisation whose departments are physically separate, a department's cameras should match only that department's people, not the whole organisation. The owner also wants to switch between COSINE and L2 matching to suit conditions: in their tests L2 at 0.95 missed more but gave no false match, and cosine at 0.45 rarely matched the wrong person.
Options:
1. Departments: a `departments` field on each vector row, filtered at search time (chosen); a partition per department, or a partition key; a lookup of department members in PostgreSQL on every batch.
2. Metric: a second collection indexed for L2 beside the cosine one; one cosine collection, with an L2 threshold converted to the equivalent cosine threshold (chosen).
Chosen: the versioned known-faces collections gain `departments`, an array of up to 16 names, filled at publish from the roster: the registered `department` plus `extra_departments`, set with `enrolment.py departments`. A camera takes its own `department`, else its location's, from the camera configuration. Each batch runs one filtered search per department present, using `array_contains_any(departments, [camera department, "all"])`; a camera without a department searches everyone. Rules (owner): no fallback to the whole organisation, a person may belong to several departments, "all" reaches every camera, and a person with no department is found only by cameras without one. For the metric, `MATCH_METRIC=COSINE|L2` in master.env, with `COSINE_THRESHOLD` (default 0.5) or `L2_THRESHOLD` (default 0.95).
Why: partitions hold one department per row, so a person in two would need their vectors copied, and a member lookup per batch adds a database round trip to every search. Face vectors are unit length (InsightFace returns them normalised), so Milvus's L2, a squared distance, equals 2 - 2 x cosine: the ranking is identical and only the cut-off differs, so L2 at t is cosine at 1 - t/2 (0.95 is 0.525). A second collection would double GPU memory and publishing for no difference. Tested on the laptop's Milvus with GPU_IVF_FLAT: department filtering, "all", cameras without a department, and the L2 identity.
Trade-off: a department change takes effect at the next publish, and a camera change at a restart. Staging searches stay unfiltered; they can only confirm a person the department search already found, so they never match outside the department, but in a large organisation other departments' crops may fill the top 5. Scores are recorded as cosine in both modes. Until a version with the field is published, a department camera matches nobody and logs why.
Revisit if: the threshold should differ per camera, or staging recall drops in a large organisation; then filter staging the same way.

## D-050: Deleting a person's face data on withdrawal or leaving (8e), run by the enrolment worker
Date: 2026-11-05   Model: Claude Opus 5.5   Decided by: owner (what is deleted and when, notice 1.2), engineering defaults (where it runs, Milvus versions, restores)
Context: notice 1.2 promises that a person's face data goes within 90 days of withdrawing or leaving, that attendance records stay, and that the camera pictures on them go 3 years after that (owner, 2026-11-03). Enrolling anyone but the owner waits for this (Face-Dataset-Collector D-025). The data sits in the bucket, three site folders, the nightly pickle, the collector's database, Milvus (versions and staging) and the roster.
Options:
1. When: a daily job that deletes within the 90 days; at once, as soon as the request is seen (chosen).
2. Where: a new service or scheduled task; the enrolment worker, which already holds the bucket key, the dataset, Milvus and the database (chosen).
3. Milvus: keep the rollback versions and delete the person's rows from each; drop every version but a new one without them (chosen).
Chosen: `DELETE /api/v1/persons/{id}/enrolment` (and withdrawing the consent an accepted enrolment rests on) ends every consent, cancels an open job and records a row in `deletions`. The worker deletes the bucket objects, the three folders, the pickle entries and the collector's rows, then publishes a version without the person and drops the rest, then removes the roster row, consents and jobs, last, so a failed run is retried whole. The `deletions` row keeps only the ID and dates; an hourly pass clears `recognition_frame` on the person's records up to the request once it is 3 years old. `recovery.py restore` re-opens the live database's deletions on the restored data.
Why: deleting at once is simpler than scheduling and keeps the promise with room to spare; a request that keeps failing stays visible as open. Rows in a released Milvus collection cannot be checked or deleted without loading it into GPU memory, and rows share the person's ID as primary key (D-030), so dropping the older versions is the only sure way; any rollback is rebuilt from the dataset. A restore that silently brought a deleted person back would break the notice.
Trade-off: a deletion cannot be undone, and it drops the rollback versions. Snapshots and backups on disk still hold whoever they held until pruned by hand; pictures in `Recognition_Frames/` (off by default) are not cleared. Attendance records have no end date and pictures of people still enrolled are kept, both pending legal advice.
Revisit if: legal advice sets an end date for attendance records or pictures, snapshots need automatic pruning at 90 days, or deletions become frequent enough that dropping rollback versions hurts.

## D-051: "Ready" means recognition works and attendance is saved
Date: 2026-11-06   Model: Claude Opus 5.5   Decided by: owner (asked for true signals, approved councils job-3 and job-4 with Codex), engineering defaults (numbers, provisional until measured)
Context: the display (Kafka-WebApp) called the system up when seven TCP ports answered. Producer-consumer, which recognises, has no port: a dead camera process or recognition thread left its container running and the screen said up. Batch errors were swallowed, and the error counter was reset every batch, so failures were never logged. `/ingest` answered OK before writing; the insert swallowed every error, a partition error rolled back earlier records of the batch and carried on, and two batches creating the same new partition lost one batch to DuplicateTable. The sender dropped a batch on any failure. InsightFace-REST's own `/health` always failed: its image never had the self-test picture.
Options:
1. keep port checks and add a Kafka heartbeat message from producer-consumer
2. an HTTP readiness check in producer-consumer, fed by what its workers actually do, with saving confirmed end to end (chosen)
Chosen: 2. Every worker writes its own progress (camera threads per frame, recognition threads per pass and per batch outcome) into shared memory made before the fork; `GET /health` on port 20010 answers starting, ready or unready with reason codes only. Unready: a streaming camera silent for 90 s, a recognition thread silent for 180 s, 3 failed batches in a row, a failing dependency check (InsightFace's self-test, Milvus, Kafka, the feedback controller, the database controller's `/health`; each check has a 10 s deadline and counts for 45 s), or the attendance sender failing. A camera being retried counts as started but is not held to a deadline; the camera's own ERROR covers it. A dead worker stops the container so Docker restarts it; a hung one is reported, not restarted, until the deadlines are measured on real cameras. `/ingest` saves a batch in one transaction with a 20 s deadline and answers 200 with `committed: true` only after the commit (400 for a payload that can never be saved, 503 when the database fails, nothing kept). One sender per process sends every batch oldest first and resends it unchanged until confirmed; the controller already skips a record it has by the record's own time, so nothing is saved twice. The controller writes a health row every 30 s; its `/health` and Docker healthcheck need the latest write to have succeeded within 90 s. A record arriving after its person's pictures were cleared (D-050) keeps none, and the clearing takes the same per-person locks. The proxy opens `/health` to displays outside the stack.
Why: an answer generated when asked needs no freshness rules, clock handling or new message format, and old displays are unaffected (Codex proposed it; a heartbeat was the first idea). Readiness taken from the workers' own progress cannot be faked by a timer, and a confirmed commit is the only proof a record was saved.
Every batch is written to a spool on disk and flushed before it is queued, deleted only when the controller confirms it, and reloaded oldest first on start, so a restart, crash or power cut loses no recognised attendance (owner, 2026-11-06: restart loss is not affordable, on any host). The spool is the client's own named volume `attendance-spool` (D-038: fsync is unreliable on Windows folder mounts), removed with the client; a payload the controller refuses moves to its `rejected/` folder instead of being deleted.
Trade-off: the spool is bounded (2 GiB, provisional): when full, or when the disk cannot be written, new batches are refused, counted and keep readiness down for 10 minutes. Frames still waiting to be recognised when the process stops are not covered (video, not yet attendance). A thread hung while opening a camera stream goes unnoticed. Readiness reports observed health, not that the camera still points where its region was drawn. Kafka-WebApp still uses its port checks until its own release (built by its session).
Revisit if: outages outlast the spool (raise it, or alert earlier), deadlines prove wrong on real cameras (measure, then enable hang restarts), or multiprocess recognition is used (only thread mode is watched).
