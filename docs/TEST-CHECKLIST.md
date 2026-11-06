# Test checklist

A change is done when these pass and the real output is pasted in the PR. CI runs the first three groups on every PR.

## Static

| Command                                                                                                                         | Pass looks like                                                                              |
|---------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| `uvx ruff@0.17.3 check --select E9,F63,F7,F82 --target-version py314 --extend-exclude STANDALONE-SERVICES,graphify-out,.venv .` | No output, exit 0                                                                            |
| `python -I mlops/check_manifest.py`                                                                                             | `manifest ok (4 unverified)`                                                                 |
| `python -I deploy/test_watch.py`                                                                                                | `watch decisions ok (12 scenarios, site config kept, old images pruned, crash loops caught)` |
| `docker compose -f docker-compose-main.yml config --quiet`                                                                      | Exit 0                                                                                       |

## Images (CI job `images`)

Each of the 8 images builds, `pip check` is clean, `cv2` and `numpy` import, entrypoints and health checks exist, and no `master.env`, `.env`, `.git` or `src/Camera-Configuration` is inside.

In `database-controller`, against a throwaway PostgreSQL, `python3 src/database_server/test_records.py` prints `records ok (saved, repeat skipped, saved after the window, host names saved, 8 parallel batches saved once, unchanged retries and midnight deduplicated, bad payloads refused, failed batches leave nothing, whole-batch deadline, cleared pictures stay cleared without deadlock, answered only after saving, health)`.
In `producer-consumer`, `python3 src/util/attendance_sender.py` prints `attendance sender ok (...)` and `python3 src/util/pipeline_health.py` prints `pipeline health ok (...)`.

In `producer-consumer`, `python3 src/util/test_camera.py` prints `camera ok (regions checked against their frame size and judged on their own pixels, 2 alerts for 500 dark frames, recovery announced once, dark frames held back before the window fills, re-sent while dark)`.

`python3 -I deploy/test_proxy.py`, on a real Caddy with stand-ins, prints `proxy ok (signed-out visitors sent to sign-in, display and WebSockets need a session, API routes reachable, API docs closed, bad host names refused)`.

In `api`, against a throwaway PostgreSQL, `python3 src/api/test_accounts.py` prints `accounts ok (role matrix, CSRF, logout, expiry, disabled users, password change, machine tokens, throttling, no key in the URL)`.

In `producer-consumer`, `python3 src/util/client_checks.py` prints `clients ok (bad IDs refused, owner names kept, two clients share no name, Milvus bound to the client's database)` (D-036).

## Client isolation (a step of the CI `checks` job, on PRs that touch provisioning or the shared services)

`python -I deploy/test_isolation.py` prints `isolation ok (2 clients: own access on 4 services, cross-client and admin actions refused, Kafka plaintext unreachable, reruns and interruptions safe, lost password stops, Milvus root replaced, holds after restart)` (D-037). It runs throwaway copies of PostgreSQL, Kafka, Milvus and MinIO and never touches the live ones.

## Secrets

gitleaks on the branch: `no leaks found`.

## Live, on this host, for service changes

```bash
docker ps --format '{{.Names}}\t{{.Status}}'      # nothing Restarting or unhealthy
curl -s localhost:6385/info                       # InsightFace: version and model names
curl -s localhost:9091/healthz                    # Milvus: OK
curl -s -o /dev/null -w '%{http_code}' localhost:9090/docs   # API: 200
curl -s -o /dev/null -w '%{http_code}' localhost:9095/       # Display: 200
tail deploy/watch.log                             # in C:\deploy\cctv: Deployed <tag>
```

For a change to `src/main.py` or its imports, also start `main.py` for real, against the running services. CI does not run it: that is how `context has already been set` shipped in v1.3.0.

## Customer path, by hand

Steps 1 to 4 passed on 2026-11-01 with a real 1080p RTSP stream through a one-off producer, and the name and portrait appeared on the display. Step 5, the ERP, is still untested.

1. Enrol one person, and point one camera at them.
2. A row appears in `recognition_results`, with the right person and camera.
3. Their name and portrait appear on the display.
4. `GET /fetch_person_data` returns the record.
5. The record reaches the ERP.
