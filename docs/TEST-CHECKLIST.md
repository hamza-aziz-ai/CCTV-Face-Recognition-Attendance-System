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

In `producer-consumer`, `python3 src/util/client_checks.py` prints `clients ok (bad IDs refused, owner names kept, two clients share no name, Milvus bound to the client's database)` (D-036).

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

Not done yet: this host has no real camera and no enrolled faces.

1. Enrol one person, and point one camera at them.
2. A row appears in `recognition_results`, with the right person and camera.
3. Their name and portrait appear on the display.
4. `GET /fetch_person_data` returns the record.
5. The record reaches the ERP.
