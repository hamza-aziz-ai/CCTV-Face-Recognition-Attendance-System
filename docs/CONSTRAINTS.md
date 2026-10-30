# Constraints

Hard rules for AI work on this repository. Stop and ask before breaking any of them.

## Never

- Never read, edit or print secrets: `.env`, `master.env` values, `.dvc/config.local`, camera credentials.
- Never force push or rewrite shared history.
- Never run a self-hosted Actions runner on this machine: it is also the dev box.
- Never delete or overwrite data folders, volumes or databases without looking at them first and asking.
- Never disable a CI check to get a PR through.
- Never pipe a download into a shell.
- Never push to `hamza-aziz-ai/hamza-aziz-ai`, or touch LinkedIn or Naukri.
- Never make this repository public.
- Never leave temporary Docker images or containers on disk after use.

## Always

- Always pin images by digest and dependencies by version.
- Always use Conventional Commit PR titles: they decide the version.
- Always use one commit per logical change, with short single-line messages.
- Always keep biometric data out of git and out of images.
- Always test a change for real, and paste real output in the PR.
- Always add a check to CI for anything that must hold: green CI is the ship gate (D-025).

## Only

- Only the owner changes `.env`.
- Only `deploy/watch.py` deploys to this host, apart from `--enroll` when the owner asks.
- Only upstream configuration changes in `STANDALONE-SERVICES/`, unless the owner asks for a code change.

## Protected areas

Ask before changing: authentication in `src/api/app.py`, Postgres schemas and data folders, Milvus collection names and indexes, recognition thresholds in `src/parameters.py`, `deploy/watch.py`, and the workflows in `.github/workflows/`.
