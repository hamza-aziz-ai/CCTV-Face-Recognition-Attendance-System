# Bug: a release run could not create its tag

**Symptom:** the release run for #40 built and pushed every image, then failed at the tag step with `gh: Resource not accessible by integration (HTTP 403)`. It opened issue #42.

**Root cause (inferred):** #41 merged while the run was building, and #41 changed `.github/workflows/automerge.yml`. GitHub refused `GITHUB_TOKEN` a tag on the older commit, whose workflow files no longer matched main. The next run, at main's head, tagged v2.0.2 without trouble. GitHub does not document this rule; the timing is the evidence.

**Fix:** when tagging fails and main has moved on, the run starts a release of main and stops without publishing (D-029). If main has not moved, the run still fails and opens an issue.

**Impact:** none lasting. v2.0.2 shipped from the next run with both PRs.

## Log

- 2026-10-31 02:02 IST: tag step failed, issue #42 opened.
- 2026-10-31 02:14 IST: next run published v2.0.2 at `cb35d1f`.
