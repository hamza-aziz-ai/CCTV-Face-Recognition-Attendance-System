# Changelog

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
