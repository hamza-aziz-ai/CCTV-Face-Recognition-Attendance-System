# Changelog

## v2.17.0 (2026-11-06)

## What's Changed
* feat(api): accept edge nodes' face crops through the API with an edge_collector machine token by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/121


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.16.2...v2.17.0

## v2.16.2 (2026-11-06)

## What's Changed
* ci: render every Mermaid diagram on a pull request that changes Markdown by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/119
* fix(collector): take each camera's crop cluster from the camera configuration, so crops from any camera are kept by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/120


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.16.1...v2.16.2

## v2.16.1 (2026-11-06)

## What's Changed
* fix(compose): put producer-consumer on the edge network, so the proxy's /health route reaches it by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/118


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.16.0...v2.16.1

## v2.16.0 (2026-11-06)

## What's Changed
* feat(roi): save the snapshot size with a region and refuse the region when the camera's resolution changes by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/114
* feat(health): true readiness for the display, attendance confirmed saved and kept on disk, and a restart when a worker dies by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/115
* fix(records): take the person locks before creating a partition, so batches never deadlock by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/117


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.15.3...v2.16.0

## v2.15.3 (2026-11-06)

## What's Changed
* fix(camera): judge darkness on the region's own pixels, stop keeping frames only to count them, and report a region that does not fit instead of reconnecting forever by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/113


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.15.2...v2.15.3

## v2.15.2 (2026-11-06)

## What's Changed
* fix(recognition): feed the recognition model RGB, as it was trained, and add a re-embed command for stored vectors by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/112


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.15.1...v2.15.2

## v2.15.1 (2026-11-05)

## What's Changed
* fix(enrolment): avoid a hidden deadlock between a deletion and a publish, keep a deletion open when a folder cannot be removed, and let a restore keep an enrolment made after a deletion by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/111


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.15.0...v2.15.1

## v2.15.0 (2026-11-05)

## What's Changed
* feat(enrolment): problem codes, per-site responsible party, and deletion on withdrawal or leaving (8e) by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/110


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.14.2...v2.15.0

## v2.14.2 (2026-11-03)

## What's Changed
* ci: build images only when what they are built from changes, and reuse the last release's images otherwise by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/108
* fix(display): pin Kafka-WebApp v0.7.4, which hides camera warnings while the whole system is shown as down by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/109


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.14.1...v2.14.2

## v2.14.1 (2026-11-03)

## What's Changed
* fix(display): pin Kafka-WebApp v0.7.3, so a refreshed page keeps the down status instead of showing ready by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/107


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.14.0...v2.14.1

## v2.14.0 (2026-11-03)

## What's Changed
* feat(display): send null for a missing portrait so the display draws a silhouette, pin Kafka-WebApp v0.7.2, and bring the model manifest up to date by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/106


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.13.0...v2.14.0

## v2.13.0 (2026-11-03)

## What's Changed
* feat(recognition): match each camera's faces within its department, and toggle between COSINE and L2 by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/105


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.12.0...v2.13.0

## v2.12.0 (2026-11-03)

## What's Changed
* feat(enrolment): enrolment API for the app, with bearer login, photos in the client's bucket and a publishing worker by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/103
* feat(enrolment): register people by organisational ID and name, and serve names to the display by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/104


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.11.0...v2.12.0

## v2.11.0 (2026-11-03)

## What's Changed
* chore(insightface): one image for amd64 and arm64 on TensorRT 26.03, to match DeepStream 9.1 by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/101
* feat(live): live view of each camera through its client's MediaMTX, behind the sign-in by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/102


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.10.0...v2.11.0

## v2.10.0 (2026-11-03)

## What's Changed
* ci: build arm64 images for the Jetson on GitHub's arm64 runners by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/98
* ci: publish the images CI tested and merge the small jobs, to save Actions minutes by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/99
* feat(camera): decode camera streams on the GPU, with the CPU as fallback by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/100


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.9.3...v2.10.0

## v2.9.3 (2026-11-02)

## What's Changed
* chore(deploy): add an owner-set tier per client (D-041) by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/89
* chore(deploy): keep release folders that containers still mount by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/90
* chore(deploy): add client snapshot, restore and remove (D-042) by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/91
* chore(edge): let an edge node use its own InsightFace-REST by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/92
* fix(display): pin Kafka-WebApp v0.4.2, which keeps names on one line by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/94
* fix(camera): keep camera passwords out of OpenCV's logs by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/93
* ci: point submodules at their latest main automatically by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/95
* chore(deps): Bump actions/checkout from 4 to 7 in the actions group by @dependabot[bot] in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/96
* ci: push submodule pins with GITHUB_TOKEN, so SUBMODULES_TOKEN stays read-only by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/97

## New Contributors
* @dependabot[bot] made their first contribution in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/96

**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.9.2...v2.9.3

## v2.9.2 (2026-11-02)

## What's Changed
* chore: run InsightFace-REST on the Jetson with TensorRT 10 by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/87
* fix: start automerge when the InsightFace image build ends by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/88


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.9.1...v2.9.2

## v2.9.1 (2026-11-02)

## What's Changed
* fix: pin the display with the single-person card fix by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/86


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.9.0...v2.9.1

## v2.9.0 (2026-11-02)

## What's Changed
* feat: fix live updates over HTTPS and theme the sign-in page by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/85


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.8.0...v2.9.0

## v2.8.0 (2026-11-01)

## What's Changed
* feat: serve each client over HTTPS behind a shared proxy (D-040) by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/84


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.7.0...v2.8.0

## v2.7.0 (2026-11-01)

## What's Changed
* chore(deploy): restart containers whose published ports die after a reboot by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/82
* feat: add per-client accounts, sessions and machine tokens to the API (D-039) by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/83


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.6.3...v2.7.0

## v2.6.3 (2026-11-01)

## What's Changed
* fix: pace lighting alerts and handle camera edge cases by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/81


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.6.2...v2.6.3

## v2.6.2 (2026-11-01)

## What's Changed
* fix: save one record when a person's batches run in parallel by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/80


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.6.1...v2.6.2

## v2.6.1 (2026-11-01)

## What's Changed
* chore(deploy): drop digest names after tagging images by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/78
* fix: save recognition records on the table the code creates by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/79


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.6.0...v2.6.1

## v2.6.0 (2026-11-01)

## What's Changed
* chore: bump the Kafka-WebApp submodule to c1c6550 by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/76
* feat(deploy): tag images pulled by digest by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/77


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.5.0...v2.6.0

## v2.5.0 (2026-11-01)

## What's Changed
* docs: add the merged PRs and today's incidents to TIMELINES.md by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/75
* feat: turn on per-client logins on the shared services, with the cutover runbook (D-036 step 3c) by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/68


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.4.0...v2.5.0

## v2.4.0 (2026-11-01)

## What's Changed
* feat: run the standalone scripts from a release bundle with a separate site folder by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/56
* fix: repair the ROI page so it draws regions into the camera configuration by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/59
* docs: record the client separation and login design (D-036) by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/60
* fix: face collector loop and display health check found in the docs review by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/67
* feat: pin Kafka-WebApp v0.3.0 so the display shows every camera by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/69
* fix: keep Postgres and Milvus data across restarts with named volumes by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/70
* docs: restyle README, FLOW.md and ARCHITECTURE.md to the documentation standard by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/66
* feat: require CLIENT_ID and give each client its own databases and topics (D-036 step 1) by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/61
* ci: retry the release image push when ghcr.io refuses it by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/72
* Add Claude Code GitHub Workflow by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/73
* feat: run each client's stack as its own compose project on a shared PostgreSQL (D-036 step 2a) by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/62
* feat(deploy): watch one site folder per client, each its own compose project (D-036 step 2b) by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/74
* feat(deploy): provision per-client logins on the shared services, with an isolation test (D-036 step 3a) by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/64
* feat: log in to the shared services with the client's own accounts (D-036 step 3b) by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/65


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.3.0...v2.4.0

## v2.3.0 (2026-11-01)

## What's Changed
* docs: record the agreed order of work in HANDOVER.md by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/58
* docs: start TIMELINES.md with real PR durations and the incidents that cost time by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/57
* feat(deploy): deploy release bundles from the registry instead of a git clone by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/53


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.2.0...v2.3.0

## v2.2.0 (2026-11-01)

## What's Changed
* docs: copy-edit the docs for US spelling, aligned tables and model names by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/49
* chore(data): add face vectors to the dataset by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/48
* ci: close release-failure issues once a later release is published by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/50
* refactor: generic GPU defaults instead of the A100 MIG layout by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/51
* feat: ship deployable artifacts instead of source to deployment hosts by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/52
* ci: skip the image builds on PRs that only change docs by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/55


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.1.0...v2.2.0

## v2.1.0 (2026-10-31)

## What's Changed
* fix: run Kafka-WebApp v0.1.2 so recognitions reach the display by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/45
* feat: version face vectors with the dataset and serve Milvus through an alias by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/46
* feat: update InsightFace-REST to 0.9.5.0 on TensorRT 11 by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/47


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.0.4...v2.1.0

## v2.0.4 (2026-10-31)

## What's Changed
* fix(ci): recover stuck merges and stale releases without a person by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/44


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.0.3...v2.0.4

## v2.0.3 (2026-10-30)

## What's Changed
* fix: keep Kafka topics across restarts and store broker data on a volume by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/43


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.0.2...v2.0.3

## v2.0.2 (2026-10-30)

## What's Changed
* Add Claude Code GitHub Workflow by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/39
* fix: correct service dependencies and healthchecks, and add Kafbat UI by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/40
* ci: let a finished Claude review also trigger auto-merge by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/41


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.0.1...v2.0.2

## v2.0.1 (2026-10-30)

## What's Changed
* ci: open an issue when a release fails by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/37
* fix: remove startup races between services by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/38


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v2.0.0...v2.0.1

## v2.0.0 (2026-10-30)

## What's Changed
* feat!: remove client names and the INSTITUTE setting by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/35
* ci: treat a check with a conclusion as finished by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/34
* fix(release): free runner disk and keep CHANGELOG.md updated by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/36


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v1.4.0...v2.0.0

## v1.4.0 (2026-10-30)

## What's Changed
* docs: record why Milvus over other vector stores by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/28
* ci: re-run cancelled CI jobs once by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/33
* feat: start the real datasets with checked enrolment by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/32


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v1.3.1...v1.4.0

## v1.3.1 (2026-10-30)

## What's Changed
* docs: add the documents required by the field guide by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/27
* docs: rewrite the defense brief in the owner's words by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/29
* fix: start producer-consumer on Python 3.14 and catch crash loops on deploy by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/30
* fix: make enrolment and fresh installs work on this host by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/31


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v1.3.0...v1.3.1

## v1.3.0 (2026-10-30)

## What's Changed
* feat: move app images to Python 3.14 with current libraries by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/24
* feat: add Kafka-WebApp as a submodule of hamza-aziz-ai/Kafka-WebApp by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/25
* feat: run Kafka-WebApp in the stack on port 9095 by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/26


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v1.2.0...v1.3.0

## v1.2.0 (2026-10-30)

## What's Changed
* feat(standalone): move Milvus to 3.0.5 following its official GPU compose file by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/22
* feat(ops): delete release images the watcher no longer needs by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/23


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v1.1.0...v1.2.0

## v1.1.0 (2026-10-30)

## What's Changed
* feat(standalone): move Kafka to Confluent Platform 8.4.0 community edition by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/21


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v1.0.0...v1.1.0

## v1.0.0 (2026-10-30)

## What's Changed
* feat!: move PostgreSQL from 12 to 18.6 by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/20


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v0.5.0...v1.0.0

## v0.5.0 (2026-10-30)

## What's Changed
* fix: first deploy on the Windows host (camera config mount, host IP, crash loop) by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/18
* feat(mlops): add a MinIO dataset store as the DVC remote by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/19


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v0.4.2...v0.5.0

## v0.4.2 (2026-10-30)

## What's Changed
* fix: make the stack's Postgres host port configurable by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/17
* fix(standalone): make the standalone services start on the Windows laptop host by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/16


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v0.4.1...v0.4.2

## v0.4.1 (2026-10-30)

## What's Changed
* fix: stop tracking master.env and keep the host's copy on deploy by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/15


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v0.4.0...v0.4.1

## v0.4.0 (2026-10-30)

## What's Changed
* feat(ops): restart standalone and app containers automatically by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/14


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v0.3.0...v0.4.0

## v0.3.0 (2026-10-30)

## What's Changed
* feat(release): publish service images to GitHub Packages (ghcr.io) by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/12
* fix(release): push images to ghcr.io one at a time by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/13


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v0.2.0...v0.3.0

## v0.2.0 (2026-10-30)

## What's Changed
* feat(ops): add pull-based deployment watcher with rollback by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/11


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/compare/v0.1.0...v0.2.0

## v0.1.0 (2026-10-30)

## What's Changed
* build: make images registry-ready (Python 3.11, baked source, real healthchecks) by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/1
* feat(mlops): add model manifest with CI drift check by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/7
* ci: auto-merge PRs once every check on the head commit passes by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/8
* ci: release automatically when merged titles call for a version bump by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/9
* feat(ops): add per-host GPU profiles, starting with the RTX 4050 laptop by @hamza-aziz-ai in https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/pull/10


**Full Changelog**: https://github.com/hamza-aziz-ai/CCTV-Face-Recognition-Attendance-System/commits/v0.1.0
