"""Deployment watcher: deploys the newest release to this machine from the container registry (D-016, D-033).

The host holds no repository and no GitHub login: only images, the release bundles, this site's config and data, and
a pull-only registry login (docker login ghcr.io). Each release publishes a bundle image (deploy/make_bundle.py) with
the compose files and every image pinned by digest; :stable points at the newest published one.

Runtime folder (this file is installed there by hand, and is never replaced by a release):
  watch.py, state.json, watch.log
  site/       this site's .env, master.env, src/Camera-Configuration/camera_configuration.json and dataset folders
  releases/   one extracted bundle per release; the current and previous ones are kept for a rollback

  pythonw watch.py            poll; deploy a newer release; roll back to the last good one on failure
  python  watch.py --enroll   first deploy, by the owner: deploy the newest release now and start watching
  python  watch.py --check    fetch and check the newest bundle without deploying it
Only the main compose stack is managed; the standalone services (InsightFace-REST, Milvus, Kafka) must already run.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state.json"
LOG = ROOT / "watch.log"
LOCK = ROOT / "watch.lock"
SITE = ROOT / "site"
RELEASES = ROOT / "releases"
CHANNEL = "ghcr.io/hamza-aziz-ai/cctv-face-recognition-deploy:stable"
IMAGE_PREFIX = "ghcr.io/hamza-aziz-ai/cctv-face-recognition-"
# Fixed project name: every release's compose file runs as the same stack, whatever folder it is extracted to
PROJECT = "cctv"
# Bind-mounted into the containers: a missing file would be created by Docker as an empty folder
SITE_FILES = [".env", "master.env", "src/Camera-Configuration/camera_configuration.json"]
SMOKE_URL = "http://localhost:9090/docs"
STABLE_SECONDS = 90
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def log(msg):
    if LOG.exists() and LOG.stat().st_size > 1_000_000:
        LOG.replace(LOG.with_suffix(".log.1"))
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def run(*cmd):
    """Run a command; on failure raise with the last line of its error output only."""
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=3600, creationflags=NO_WINDOW)
    if p.returncode != 0:
        last = (p.stderr.strip() or p.stdout.strip()).splitlines()[-1:] or ["no output"]
        raise RuntimeError(f"{' '.join(cmd[:3])} failed: {last[0][:300]}")
    return p.stdout.strip()


def notify(msg):
    subprocess.run(["msg", os.environ.get("USERNAME", "*"), msg], capture_output=True, creationflags=NO_WINDOW)


def compose(tag):
    return ["docker", "compose", "-p", PROJECT, "--project-directory", str(SITE),
            "-f", str(RELEASES / tag / "docker-compose-main.yml")]


def latest_release():
    """The release :stable points at, and its bundle by digest; None while nothing is published."""
    try:
        run("docker", "pull", "-q", CHANNEL)
    except RuntimeError as e:
        if "not found" in str(e) or "manifest unknown" in str(e):
            return None
        raise
    tag = run("docker", "inspect", "--format", '{{index .Config.Labels "org.opencontainers.image.version"}}', CHANNEL)
    ref = run("docker", "inspect", "--format", "{{index .RepoDigests 0}}", CHANNEL)
    return tag, ref


def check_bundle(folder, tag):
    """Refuse a bundle that is not for this release, or whose images are not ours and pinned by digest."""
    manifest = json.loads((folder / "release-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or manifest.get("release") != tag or not manifest.get("images"):
        raise RuntimeError(f"bundle manifest is not a schema-1 manifest for {tag}")
    for ref, pinned in manifest["images"].items():
        if not re.fullmatch(rf"{re.escape(IMAGE_PREFIX)}[a-z-]+@sha256:[0-9a-f]{{64}}", pinned):
            raise RuntimeError(f"bundle pins {ref} to {pinned}, not one of our images by digest")
    text = (folder / "docker-compose-main.yml").read_text(encoding="utf-8")
    if "${IMAGE_TAG" in text or "build:" in text or re.search(r"^\s*- \.:", text, re.M):
        raise RuntimeError("bundle compose file builds, mounts the checkout, or has an unpinned app image")
    return manifest


def stage(tag, ref):
    """Copy the bundle out of its image into releases/<tag>, checked, without ever running the image."""
    dest = RELEASES / tag
    if dest.exists():
        return check_bundle(dest, tag)
    tmp = RELEASES / f".{tag}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    RELEASES.mkdir(exist_ok=True)
    container = run("docker", "create", ref)
    try:
        run("docker", "cp", f"{container}:/bundle", str(tmp))
    finally:
        run("docker", "rm", container)
    try:
        manifest = check_bundle(tmp, tag)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    tmp.rename(dest)  # a half-copied bundle never appears under its release name
    return manifest


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


def project_containers(*filters, fmt="{{.ID}}"):
    return run("docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={PROJECT}", *filters, "--format", fmt)


def stable():
    """Fail if a service is crash-looping: with a restart policy and no healthcheck, up --wait counts it as started."""
    time.sleep(STABLE_SECONDS)
    down = project_containers("--filter", "status=restarting", "--filter", "status=exited",
                              fmt='{{.Label "com.docker.compose.service"}}')
    if down:
        raise RuntimeError(f"not stable after {STABLE_SECONDS}s: {', '.join(down.split())}")


def start(tag):
    """Start the release's stack from its bundle, with this site's config and data."""
    run(*compose(tag), "up", "-d", "--pull", "missing", "--no-build", "--wait", "--wait-timeout", "600")
    smoke()
    stable()


def deploy(tag, ref):
    stage(tag, ref)
    start(tag)


def prune(keep):
    """Delete bundles and our images that the kept releases do not use. Dev builds (no digest) and the standalone
    InsightFace image stay, and a failure never fails a deploy."""
    try:
        used = {run("docker", "inspect", "--format", "{{index .RepoDigests 0}}", CHANNEL)}  # the current bundle image
        for tag in keep:
            if tag and (RELEASES / tag).exists():
                used |= set(check_bundle(RELEASES / tag, tag)["images"].values())
        for folder in RELEASES.iterdir() if RELEASES.exists() else []:
            if folder.name not in keep:
                shutil.rmtree(folder, ignore_errors=True)
        stale = set()
        for line in run("docker", "images", "--digests", "--format", "{{.Repository}}@{{.Digest}} {{.ID}}").splitlines():
            ref, image_id = line.split()
            if ref.startswith(IMAGE_PREFIX) and "insightface-rest" not in ref and not ref.endswith("@<none>") and ref not in used:
                stale.add(image_id)
        if stale:
            run("docker", "rmi", "-f", *sorted(stale))
            log(f"Removed {len(stale)} old release images")
    except Exception as e:
        log(f"Cleanup failed: {e}")


def save(state):
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def problem(state, msg):
    """Log a problem that stops deploys; notify once per new problem, not every 10 minutes."""
    log(msg)
    if state is not None and state.get("problem") != msg:
        state["problem"] = msg
        save(state)
        notify(f"CCTV deploy watcher: {msg}. See watch.log in the deploy folder.")


def watch(enroll=False, check=False):
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else None
    if state is None and not (enroll or check):
        log("Not enrolled; the owner runs: python watch.py --enroll")
        return 0
    try:
        run("docker", "info")
    except RuntimeError:
        log("Docker is not running; skipped.")
        return 0
    try:
        release = latest_release()
    except RuntimeError as e:  # most often an expired or revoked registry token
        problem(state, f"cannot read {CHANNEL}: {e}")
        return 1
    if not release:
        log("No published release yet.")
        return 0
    tag, ref = release
    if check:
        stage(tag, ref)
        print(f"{tag}: bundle {ref} checked, in {RELEASES / tag}")
        return 0
    missing = [name for name in SITE_FILES if not (SITE / name).is_file()]
    if missing:
        problem(state, f"site config missing: {', '.join(missing)} under {SITE}")
        return 1
    state = state or {"current": None, "failed": []}
    state.pop("problem", None)
    if not enroll:
        if tag == state["current"] or tag in state["failed"]:
            save(state)
            return 0
        # The owner stopped the stack on purpose; never start it behind their back.
        if state["current"] and not project_containers("--filter", "status=running"):
            log(f"Stack is stopped; not deploying {tag}. Start it, or run --enroll, to resume.")
            return 0
    prev = state["current"]
    log(f"Deploying {tag} (current: {prev})")
    try:
        deploy(tag, ref)
    except Exception as e:  # any failure, including a crash mid-deploy, ends in a rollback
        log(f"Deploy of {tag} failed: {e}")
        state["failed"].append(tag)
        try:
            if prev:
                start(prev)  # its bundle and images are still here, so no network is needed
                outcome = f"rolled back to {prev}"
            else:
                # Restart policies would keep a broken first deploy crash-looping
                running = project_containers("--filter", "status=running").split()
                if running:
                    run("docker", "stop", *running)
                outcome = "nothing to roll back to; stack stopped"
        except Exception as e2:
            outcome = f"ROLLBACK TO {prev} FAILED: {e2}" if prev else f"nothing to roll back to; STOP FAILED: {e2}"
        log(outcome)
        save(state)
        notify(f"CCTV deploy of {tag} failed; {outcome}. See watch.log in the deploy folder.")
        return 1
    state["current"] = tag
    save(state)
    log(f"Deployed {tag}")
    prune({tag, prev})  # the previous release stays for a rollback
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
        return watch(enroll="--enroll" in sys.argv, check="--check" in sys.argv)
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
