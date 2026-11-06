"""Deployment watcher: deploys the newest release to this machine from the container registry (D-016, D-033).

The host holds no repository and no GitHub login: only images, the release bundles, this site's config and data, and
a pull-only registry login (docker login ghcr.io). Each release publishes a bundle image (deploy/make_bundle.py) with
the compose files and every image pinned by digest; :stable points at the newest published one.

Runtime folder (this file is installed there by hand, and is never replaced by a release):
  watch.py, watch.log
  sites/<client>/   one per client this host serves (D-036): its .env, master.env (CLIENT_ID=<client>),
                    src/Camera-Configuration/camera_configuration.json, dataset folders, logs, and state.json
  releases/         one extracted bundle per release; every client's current and previous ones are kept for a rollback

  pythonw watch.py                   poll; deploy a newer release to each enrolled client; roll back on failure
  python  watch.py --enroll CLIENT   first deploy of a client, by the owner: deploy the newest release now, start watching
  python  watch.py --check           fetch and check the newest bundle without deploying it
sites/<client>/layout, set by the owner like tier (D-052): absent or full runs the whole stack here; edge, on an edge node,
only capture (docker-compose-edge.yml); central, for a client an edge captures, the rest (docker-compose-central.yml added).
A rollback never changes it: a release that does not offer the site's layout is refused, rollback included.
On Linux (an edge node) run it from cron or a systemd timer with python3; notifications are only logged there.
Each client is its own compose project: cctv for the owner, cctv-<client> for the others. One client's failure,
rollback or stopped stack never touches another's. Only the main compose stack is managed; the standalone services
(InsightFace-REST, Milvus, Kafka, PostgreSQL) must already run.
"""
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "watch.log"
LOCK = ROOT / "watch.lock"
SITES = ROOT / "sites"
RELEASES = ROOT / "releases"
CHANNEL = "ghcr.io/hamza-aziz-ai/cctv-face-recognition-deploy:stable"
IMAGE_PREFIX = "ghcr.io/hamza-aziz-ai/cctv-face-recognition-"
# The bundle image is files only (FROM scratch, never run) and is published for amd64; an arm64 edge node (D-052) asks
# for that one too, or its pull finds no image for its own platform
BUNDLE_PLATFORM = "linux/amd64"
# Same rule as src/parameters.py; the owner's stack keeps the project name it had before D-036
CLIENT_ID = re.compile(r"[a-z][a-z0-9]{2,29}")
OWNER = "owner"
BASE_TIER = "standard"
LAYOUTS = {"full": ["docker-compose-main.yml"], "central": ["docker-compose-main.yml", "docker-compose-central.yml"],
           "edge": ["docker-compose-edge.yml"]}
BASE_LAYOUT = "full"
# Off on a central site (docker-compose-central.yml); up leaves their old containers running, so start removes them
EDGE_OWNED = ["mfr-cctv-producer-consumer", "mfr-database-controller", "mfr-feedback-controller"]
# Bind-mounted into the containers: a missing file would be created by Docker as an empty folder
SITE_FILES = [".env", "master.env", "src/Camera-Configuration/camera_configuration.json"]
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
    try:
        subprocess.run(["msg", os.environ.get("USERNAME", "*"), msg], capture_output=True, creationflags=NO_WINDOW)
    except OSError:  # no msg outside Windows: the log line before every notification is the record
        pass


def project(site):
    """Fixed per client: every release's compose file runs as the same stack, whatever folder it is extracted to."""
    return "cctv" if site.name == OWNER else f"cctv-{site.name}"


def setting(path, key, default=None):
    """One key of an env file; the rest (credentials) is never kept."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    values = [line.split("=", 1)[1].strip().strip("'\"") for line in lines if line.startswith(f"{key}=")]
    return values[-1] if values else default


def layout(site):
    """The owner-set layout (D-052). No container mounts this file; a client without one runs the whole stack here."""
    file = site / "layout"
    return file.read_text(encoding="utf-8").strip() if file.is_file() else BASE_LAYOUT


def compose(tag, site):
    files = [arg for name in LAYOUTS[layout(site)] for arg in ("-f", str(RELEASES / tag / name))]
    return ["docker", "compose", "-p", project(site), "--project-directory", str(site), *files]


def latest_release():
    """The release :stable points at, and its bundle by digest; None while nothing is published."""
    try:
        run("docker", "pull", "-q", "--platform", BUNDLE_PLATFORM, CHANNEL)
    except RuntimeError as e:
        if ("not found" in str(e) or "manifest unknown" in str(e)) and "no matching manifest" not in str(e):
            return None
        raise
    tag = run("docker", "inspect", "--format", '{{index .Config.Labels "org.opencontainers.image.version"}}', CHANNEL)
    ref = run("docker", "inspect", "--format", "{{index .RepoDigests 0}}", CHANNEL)
    run("docker", "tag", CHANNEL, f"{CHANNEL.rsplit(':', 1)[0]}:{tag}")  # keeps a name once :stable moves on
    return tag, ref


def check_bundle(folder, tag):
    """Refuse a bundle that is not for this release, or whose images are not ours and pinned by digest."""
    manifest = json.loads((folder / "release-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or manifest.get("release") != tag or not manifest.get("images"):
        raise RuntimeError(f"bundle manifest is not a schema-1 manifest for {tag}")
    for ref, pinned in manifest["images"].items():
        if not re.fullmatch(rf"{re.escape(IMAGE_PREFIX)}[a-z-]+@sha256:[0-9a-f]{{64}}", pinned):
            raise RuntimeError(f"bundle pins {ref} to {pinned}, not one of our images by digest")
    for path in folder.glob("docker-compose*.yml"):
        text = path.read_text(encoding="utf-8")
        if "${IMAGE_TAG" in text or "build:" in text or re.search(r"^\s*- \.:", text, re.M):
            raise RuntimeError(f"bundle {path.name} builds, mounts the checkout, or has an unpinned app image")
    return manifest


def stage(tag, ref):
    """Copy the bundle out of its image into releases/<tag>, checked, without ever running the image."""
    dest = RELEASES / tag
    if dest.exists():
        return check_bundle(dest, tag)
    tmp = RELEASES / f".{tag}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    RELEASES.mkdir(exist_ok=True)
    container = run("docker", "create", "--platform", BUNDLE_PLATFORM, ref)
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


def smoke(site):
    url = f"http://localhost:{setting(site / '.env', 'API_PORT', '9090')}/docs"  # this client's own API port
    for _ in range(30):
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                if r.status == 200:
                    return
        except OSError:
            pass
        time.sleep(10)
    raise RuntimeError(f"smoke test failed: no HTTP 200 from {url} within 5 minutes")


def project_containers(site, *filters, fmt="{{.ID}}"):
    return run("docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={project(site)}", *filters,
               "--format", fmt)


def stable(site):
    """Fail if a service is crash-looping: with a restart policy and no healthcheck, up --wait counts it as started."""
    time.sleep(STABLE_SECONDS)
    down = project_containers(site, "--filter", "status=restarting", "--filter", "status=exited",
                              fmt='{{.Label "com.docker.compose.service"}}')
    if down:
        raise RuntimeError(f"not stable after {STABLE_SECONDS}s: {', '.join(down.split())}")


def port_answers(port):
    """Whether something behind a published port speaks HTTP; any status counts, because the page may not exist."""
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/", timeout=5):
            return True
    except urllib.error.HTTPError:
        return True
    except (OSError, http.client.HTTPException):
        return False


def heal_ports(site):
    """After a reboot Docker Desktop can leave a healthy container with a dead published port, so restart that container. Only healthy ones: a container still starting or failing is not a port problem."""
    lines = project_containers(site, "--filter", "health=healthy", fmt="{{.ID}} {{.Ports}}").splitlines()
    dead = [line.split()[0] for line in lines if not all(port_answers(p) for p in set(re.findall(r":(\d+)->", line)))]
    if dead:
        run("docker", "restart", *dead)
        log(f"[{site.name}] Restarted {len(dead)} healthy containers whose published ports were dead")


def tag_images(tag):
    """Give a release's images their tag and drop their digest name, which Docker Desktop lists as a <none> row. Runs
    every poll, so an image that was not running last time is retried. Cosmetic: a failure never fails a deploy."""
    try:
        folder = RELEASES / tag
        names = dict(check_bundle(folder, tag)["images"])
        for path in [*folder.glob("docker-compose*.yml"), *folder.glob("STANDALONE-SERVICES/*/docker-compose*.yml")]:
            for name, digest in re.findall(r"(\S+:[^@\s]+)@(sha256:[0-9a-f]{64})", path.read_text(encoding="utf-8")):
                names[name] = f"{name.rsplit(':', 1)[0]}@{digest}"
    except (OSError, RuntimeError) as e:
        log(f"Image tagging skipped: {e}")
        return
    for name, pinned in names.items():
        try:
            run("docker", "tag", pinned, name)
            # With no container on the image, rmi would delete the image itself, tag included
            if run("docker", "ps", "-q", "--filter", f"ancestor={name}"):
                run("docker", "rmi", "-f", pinned)
        except RuntimeError:  # not on this host, or the digest name is already gone
            pass


def start(tag, site):
    """Start the release's stack from its bundle, with this client's config and data. Deploys and rollbacks both come here,
    so a release without this site's layout is never started: bundles from before D-052 offer only the full one."""
    if layout(site) not in check_bundle(RELEASES / tag, tag).get("layouts", [BASE_LAYOUT]):
        raise RuntimeError(f"{tag} does not offer layout {layout(site)!r}")
    subprocess.run(["docker", "network", "create", "cctv-edge"], capture_output=True, creationflags=NO_WINDOW)  # fails harmlessly once it exists
    if layout(site) == "central":  # a site switched from full would otherwise keep capturing beside its edge node
        run(*compose(tag, site), "rm", "--stop", "--force", *EDGE_OWNED)
    run(*compose(tag, site), "up", "-d", "--pull", "missing", "--no-build", "--wait", "--wait-timeout", "600")
    if layout(site) != "edge":  # an edge node has no API; up --wait has already waited for every healthcheck
        smoke(site)
    stable(site)
    tag_images(tag)


def tier(site):
    """The owner-set tier (D-041). No container mounts this file; a client without one gets the base tier."""
    file = site / "tier"
    return file.read_text(encoding="utf-8").strip() if file.is_file() else BASE_TIER


def deploy(tag, ref, site):
    manifest = stage(tag, ref)
    if tier(site) not in manifest.get("tiers", [BASE_TIER]):  # bundles older than D-041 list no tiers
        raise RuntimeError(f"{tag} does not offer tier {tier(site)!r}")
    start(tag, site)


def mounted():
    """Releases a container still mounts: the shared services run from the bundle that started them, and lose their config
    at the next restart if it goes."""
    ids = run("docker", "ps", "-aq").split()
    sources = run("docker", "inspect", "--format", "{{range .Mounts}}{{.Source}} {{end}}", *ids) if ids else ""
    return set(re.findall(r"releases[/\\]([^/\\\s]+)[/\\]", sources))


def prune(keep):
    """Delete bundles and our images that the kept releases do not use. Dev builds (no digest) and the standalone
    InsightFace image stay, and a failure never fails a deploy."""
    try:
        used = {run("docker", "inspect", "--format", "{{index .RepoDigests 0}}", CHANNEL)}  # the current bundle image
        for tag in keep:
            if tag and (RELEASES / tag).exists():
                used |= set(check_bundle(RELEASES / tag, tag)["images"].values())
        in_use = mounted()
        for folder in RELEASES.iterdir() if RELEASES.exists() else []:
            if folder.name not in keep | in_use:
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


def load(site):
    path = site / "state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save(site, state):
    (site / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


def problem(site, state, msg):
    """Log a problem that stops deploys; notify once per new problem, not every 10 minutes."""
    log(f"[{site.name}] {msg}")
    if state is not None and state.get("problem") != msg:
        state["problem"] = msg
        save(site, state)
        notify(f"CCTV deploy watcher, {site.name}: {msg}. See watch.log in the deploy folder.")


def sites():
    return sorted(p for p in SITES.iterdir() if p.is_dir()) if SITES.exists() else []


def kept():
    """Every client's current and previous release, so one client's cleanup never deletes another's rollback."""
    states = [load(site) or {} for site in sites()]
    return {tag for state in states for tag in (state.get("current"), state.get("previous")) if tag}


def watch_site(site, tag, ref, enroll=False):
    """Bring one client to tag; on failure roll back that client only. Returns 1 on a problem, else 0."""
    state = load(site)
    if state is None and not enroll:
        log(f"[{site.name}] Not enrolled; the owner runs: python watch.py --enroll {site.name}")
        return 0
    client = setting(site / "master.env", "CLIENT_ID")
    # The folder is the client's identity (state, data, project name), so it must agree with what the services use
    if not CLIENT_ID.fullmatch(site.name) or client != site.name:
        problem(site, state, f"folder {site.name} has CLIENT_ID={client!r} in master.env; both must be the same valid ID")
        return 1
    missing = [name for name in SITE_FILES if not (site / name).is_file()]
    if missing:
        problem(site, state, f"site config missing: {', '.join(missing)} under {site}")
        return 1
    state = state or {"current": None, "previous": None, "failed": []}
    state.pop("problem", None)
    if not enroll:
        if tag == state["current"] or tag in state["failed"]:
            save(site, state)
            tag_images(state["current"])
            heal_ports(site)
            return 0
        # The owner stopped the stack on purpose; never start it behind their back.
        if state["current"] and not project_containers(site, "--filter", "status=running"):
            log(f"[{site.name}] Stack is stopped; not deploying {tag}. Start it, or run --enroll {site.name}, to resume.")
            return 0
    prev = state["current"]
    log(f"[{site.name}] Deploying {tag} (current: {prev})")
    try:
        deploy(tag, ref, site)
    except Exception as e:  # any failure, including a crash mid-deploy, ends in a rollback
        log(f"[{site.name}] Deploy of {tag} failed: {e}")
        state["failed"].append(tag)
        try:
            if prev:
                start(prev, site)  # its bundle and images are still here, so no network is needed
                outcome = f"rolled back to {prev}"
            else:
                # Restart policies would keep a broken first deploy crash-looping
                running = project_containers(site, "--filter", "status=running").split()
                if running:
                    run("docker", "stop", *running)
                outcome = "nothing to roll back to; stack stopped"
        except Exception as e2:
            outcome = f"ROLLBACK TO {prev} FAILED: {e2}" if prev else f"nothing to roll back to; STOP FAILED: {e2}"
        log(f"[{site.name}] {outcome}")
        save(site, state)
        notify(f"CCTV deploy of {tag} for {site.name} failed; {outcome}. See watch.log in the deploy folder.")
        return 1
    if prev != tag:  # an enrolled redeploy of the same release keeps the older rollback
        state["previous"] = prev
    state["current"] = tag
    save(site, state)
    log(f"[{site.name}] Deployed {tag}")
    prune(kept())
    return 0


def watch(enroll=None, check=False):
    """One poll: every client under sites/, or only the one being enrolled."""
    targets = [site for site in sites() if enroll in (None, site.name)]
    if enroll and not targets:
        print(f"No site folder {SITES / enroll}")
        return 1
    if not (enroll or check or any(load(site) for site in targets)):
        log("No client enrolled; the owner runs: python watch.py --enroll CLIENT")
        return 0
    try:
        run("docker", "info")
    except RuntimeError:
        log("Docker is not running; skipped.")
        return 0
    try:
        release = latest_release()
    except RuntimeError as e:  # most often an expired or revoked registry token: it stops every client
        for site in targets:
            problem(site, load(site), f"cannot read {CHANNEL}: {e}")
        return 1
    if not release:
        log("No published release yet.")
        return 0
    tag, ref = release
    if check:
        stage(tag, ref)
        print(f"{tag}: bundle {ref} checked, in {RELEASES / tag}")
        return 0
    return max([watch_site(site, tag, ref, enroll=bool(enroll)) for site in targets], default=0)


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
        if sys.argv[-1:] == ["--enroll"]:
            sys.exit("Usage: python watch.py --enroll CLIENT")
        enroll = sys.argv[sys.argv.index("--enroll") + 1] if "--enroll" in sys.argv else None
        return watch(enroll=enroll, check="--check" in sys.argv)
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
