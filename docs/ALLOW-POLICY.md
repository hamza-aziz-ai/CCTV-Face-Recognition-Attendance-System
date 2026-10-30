# Allow policy

What an AI tool may do on this repository. Review it when the project or its risk changes.

## Safe to allow

- Reading code and docs, listing and searching files.
- Running tests and linters.
- Reading logs and `docker ps`.
- Editing on a feature branch.
- Temporary containers with `--rm`, deleted with their images afterwards.
- Pushing a feature branch and opening a PR.

## Pause and read

- Edits across many files.
- Config, compose or workflow changes.
- Adding or upgrading a dependency.
- Changing authentication or permissions.
- Starting, stopping or recreating running services.
- Writing to a database or a data folder.
- Calling a new external host.
- Deleting files, images, containers or volumes that the AI did not create.
- Changing settings of any GitHub repository.

## Never auto-allow

- Reading or editing `.env`, `.dvc/config.local` or real camera configuration.
- Production database commands.
- Deploy commands: the watcher deploys.
- Force push or history rewrites on shared branches.
- Disabling tests or security checks.
- `rm -rf` outside the session scratch folder.
- Piping downloads into a shell.
- Authentication code without review.

The rule of thumb: the harder an action is to undo, the less it deserves a fast click. See [CONSTRAINTS.md](CONSTRAINTS.md) for the rules this policy serves.
