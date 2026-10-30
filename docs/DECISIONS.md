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
