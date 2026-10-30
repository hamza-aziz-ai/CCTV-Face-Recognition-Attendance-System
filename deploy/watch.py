"""Deployment watcher: deploys the newest GitHub Release of this repo to this machine (D-016).

Runs from a dedicated deploy clone, never the dev checkout, every few minutes from Windows Task Scheduler:
  pythonw deploy\\watch.py            poll; deploy a newer release; roll back to the last good one on failure
  python  deploy\\watch.py --enroll   first deploy, by the owner: deploy the newest release now and start watching
State is kept in deploy/state.json and steps are logged to deploy/watch.log (both git-ignored).
Only the main compose stack is managed; the standalone services (InsightFace-REST, Milvus, Kafka) must already run.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "deploy" / "state.json"
LOG = ROOT / "deploy" / "watch.log"
LOCK = ROOT / "deploy" / "watch.lock"
COMPOSE = ["docker", "compose", "-f", "docker-compose-main.yml"]
# Release images are pulled from ghcr.io once; a rollback reuses the ones already here (tags are never moved).
UP = COMPOSE + ["up", "-d", "--pull", "missing", "--no-build", "--wait", "--wait-timeout", "600"]
SMOKE_URL = "http://localhost:9090/docs"
# Unattended fetches authenticate through the owner's gh login instead of an SSH key that may need a passphrase.
GIT = ["git", "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential"]
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def log(msg):
    if LOG.exists() and LOG.stat().st_size > 1_000_000:
        LOG.replace(LOG.with_suffix(".log.1"))
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def run(*cmd, env=None):
    """Run a command in the deploy clone; on failure raise with the last line of its error output only."""
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=3600,
                       env={**os.environ, **(env or {})}, creationflags=NO_WINDOW)
    if p.returncode != 0:
        last = (p.stderr.strip() or p.stdout.strip()).splitlines()[-1:] or ["no output"]
        raise RuntimeError(f"{' '.join(cmd[:3])} failed: {last[0][:300]}")
    return p.stdout.strip()


def notify(msg):
    subprocess.run(["msg", os.environ.get("USERNAME", "*"), msg], capture_output=True, creationflags=NO_WINDOW)


def latest_release():
    return run("gh", "release", "list", "--exclude-drafts", "--exclude-pre-releases", "--limit", "1",
               "--json", "tagName", "--jq", ".[0].tagName // empty") or None


def smoke():
    for _ in range(30):
        try:
            with urllib.request.urlopen(SMOKE_URL, timeout=5) as r:
                if r.status == 200:
                    return
        except OSError:
            pass
        time.sleep(10)
    raise RuntimeError(f"smoke test failed: no HTTP 200 from {SMOKE_URL} within 5 minutes")


def start(tag):
    """Check out the tag and start the images CI built and published for it."""
    # master.env is this site's config. Older tags still track it, so a checkout would delete or overwrite it.
    site = ROOT / "master.env"
    keep = site.read_bytes() if site.exists() else None
    try:
        run("git", "checkout", "--force", "--detach", tag)
    finally:
        if keep is not None:
            site.write_bytes(keep)
    run(*UP, env={"IMAGE_TAG": tag})
    smoke()


def deploy(tag):
    run(*GIT, "fetch", "--tags", "--force", "origin")
    # Only releases on main; a tag pointing anywhere else is refused.
    run("git", "merge-base", "--is-ancestor", tag, "origin/main")
    start(tag)


def save(state):
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def watch(enroll=False):
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else None
    if state is None and not enroll:
        log("Not enrolled; the owner runs: python deploy/watch.py --enroll")
        return 0
    try:
        run("docker", "info")
    except RuntimeError:
        log("Docker is not running; skipped.")
        return 0
    tag = latest_release()
    if not tag:
        log("No published release yet.")
        return 0
    state = state or {"current": None, "failed": []}
    if not enroll:
        if tag == state["current"] or tag in state["failed"]:
            return 0
        # The owner stopped the stack on purpose; never start it behind their back.
        if state["current"] and not run(*COMPOSE, "ps", "-q"):
            log(f"Stack is stopped; not deploying {tag}. Start it, or run --enroll, to resume.")
            return 0
    prev = state["current"]
    log(f"Deploying {tag} (current: {prev})")
    try:
        deploy(tag)
    except Exception as e:  # any failure, including a crash mid-deploy, ends in a rollback
        log(f"Deploy of {tag} failed: {e}")
        state["failed"].append(tag)
        try:
            if prev:
                start(prev)
                outcome = f"rolled back to {prev}"
            else:
                # Restart policies would keep a broken first deploy crash-looping
                run(*COMPOSE, "stop")
                outcome = "nothing to roll back to; stack stopped"
        except Exception as e2:
            outcome = f"ROLLBACK TO {prev} FAILED: {e2}" if prev else f"nothing to roll back to; STOP FAILED: {e2}"
        log(outcome)
        save(state)
        notify(f"CCTV deploy of {tag} failed; {outcome}. See deploy/watch.log in the deploy clone.")
        return 1
    state["current"] = tag
    save(state)
    log(f"Deployed {tag}")
    return 0


def main():
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        # A crashed run leaves its lock behind; a lock older than any deploy can take is stale.
        if time.time() - LOCK.stat().st_mtime < 7200:
            return 0
        LOCK.unlink()
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    try:
        return watch(enroll="--enroll" in sys.argv)
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
