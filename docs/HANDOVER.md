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
- Repo settings applied: squash merge only (PR title and body become the commit), automatically delete head branches. Dependabot alerts, Dependabot security updates and the read-only default workflow token were already on.

In progress:
- PR #1 (`ci/docker-packaging`): step 2 commits are local-verified (8 builds and smoke tests pass); waiting for the first `ci` run on GitHub.

Broken or risky:
- `src/main.py` deletes Kafka topics at startup. Pending feedback may be lost on restart (unverified).
- `src/automatic-vector-db-updation/milvus_updater.py` deletes old vectors, swallows insert failures and still marks the rows processed. This loses vectors silently.
- Python 3.11 has only been verified by build, `pip check` and import smoke tests; no live pipeline run yet.
- Dependabot reports 7 vulnerabilities (4 high, 3 moderate), not yet triaged.

Next:
- Actions budget (account Billing page, manual). Allow Actions to create PRs only when `release.yml` lands.
- `.github/dependabot.yml` for github-actions.
- `docker-compose.dev.yml`, then remove `build-docker-images.sh` and update the README.
- Model manifest, DockerHub repo and secrets, then `release.yml` with release-please.

Do not touch:
- `STANDALONE-SERVICES/` upstream services (InsightFace-REST, Milvus, Kafka).
- The `Kafka-WebApp` submodule (belongs to another account).
- Production hosts: no deployment automation until the phase-two criteria in the plan are met.
