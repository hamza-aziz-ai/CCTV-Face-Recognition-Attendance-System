# Bug: first watcher deploy failed

**Symptom:** v0.4.2 deploy failed with `dependency failed to start: container cctv-face-recognition-database-controller is unhealthy`.

**Repro:** `python deploy\watch.py --enroll` on the Windows host.

**Root causes**

1. Camera configuration was never mounted. D-005 keeps it out of the images, but the compose file had no mount: `FileNotFoundError: ... camera_configuration.json`.
2. `get_ip.sh` needs `ip`, which Git Bash lacks, so `IP_ADDRESS` was `127.0.0.1`. Inside a container that is the container itself: `Connection refused`.
3. With no earlier release, restart policies kept the broken stack crash-looping.

**Fix:** PR #18: mount read-only into 3 services, PowerShell fallback in `get_ip.sh`, `compose stop` when a first deploy fails. Kafka had to be recreated with the real IP.

**Verification:** v0.5.0 deployed; all containers healthy; `api /docs: 200`.

## Log

- 2026-10-30 20:28: v0.4.2 failed, stack stopped by hand.
- 2026-10-30 20:58: v0.5.0 deployed.
