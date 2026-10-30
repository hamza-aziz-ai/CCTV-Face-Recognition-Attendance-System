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
- Repo settings applied: squash merge only (PR title and body become the commit), automatically delete head branches. Dependabot alerts, Dependabot security updates and the read-only default workflow token were already on.

In progress:
- PR #1 (`ci/docker-packaging`): step 2 commits are local-verified (8 builds and smoke tests pass); waiting for the first `ci` run on GitHub.

Broken or risky:
- `src/main.py` deletes Kafka topics at startup. Pending feedback may be lost on restart (unverified).
- `src/automatic-vector-db-updation/milvus_updater.py` deletes old vectors, swallows insert failures and still marks the rows processed. This loses vectors silently.
- Python 3.11 has only been verified by build, `pip check` and import smoke tests; no live pipeline run yet.
- Existing hosts must rebuild images before the next `up` after merging PR #1. The old `v-beta` images contain no code, and the base compose no longer mounts `./src`.
- Dependabot reports 7 vulnerabilities (4 high, 3 moderate), not yet triaged.

Next:
- Actions budget (account Billing page, manual). Allow Actions to create PRs only when `release.yml` lands.
- Map the producer-consumer runtime files to explicit mounts, replacing its whole-repo `.` mount.
- Fill the 4 null manifest values from the GPU host (commands are in the manifest's `unverified` block).
- DockerHub repo and secrets, then `release.yml` with release-please, gated on `check_manifest.py --release`.

Do not touch:
- `STANDALONE-SERVICES/` upstream services (InsightFace-REST, Milvus, Kafka).
- The `Kafka-WebApp` submodule (belongs to another account).
- Production hosts: no deployment automation until the phase-two criteria in the plan are met.
