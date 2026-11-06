"""Decision tests for deploy/watch.py with Docker and the registry faked out. Run: python -I deploy/test_watch.py"""
import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_bundle  # noqa: E402
import watch  # noqa: E402


def site(root, name="owner", missing=(), client=None):
    """A client's site folder; master.env names the client, the other files only need to exist."""
    folder = root / "sites" / name
    for file in watch.SITE_FILES:
        if file not in missing:
            (folder / file).parent.mkdir(parents=True, exist_ok=True)
            (folder / file).write_text(f"CLIENT_ID={client or name}\n" if file == "master.env" else "x")
    return folder


def poll(tmp, states, latest, running=(), fail=(), rollback_fails=False, enroll=None):
    """Run one poll over the sites under tmp with the given states. running: clients whose stack is up; fail: clients
    whose deploy fails. Returns (exit code, saved states, deploys, rollback starts, notifications, stops, kept)."""
    calls = {"deploy": [], "start": [], "notify": [], "stop": 0, "kept": []}

    def fake_run(*cmd):
        calls["stop"] += cmd[:2] == ("docker", "stop")
        projects = [arg.split("=", 2)[2] for arg in cmd if arg.startswith("label=com.docker.compose.project=")]
        up = {watch.project(tmp / "sites" / name) for name in running}
        return "abc123" if "status=running" in cmd and projects and projects[0] in up else ""

    def fake_deploy(tag, ref, folder):
        assert ref == f"bundle@{tag}"
        calls["deploy"].append((folder.name, tag))
        if folder.name in fail:
            raise RuntimeError("up failed")

    def fake_start(tag, folder):
        calls["start"].append((folder.name, tag))
        if rollback_fails:
            raise RuntimeError("rollback failed")

    with mock.patch.multiple(watch, SITES=tmp / "sites", LOG=tmp / "watch.log", run=fake_run,
                             latest_release=lambda: latest and (latest, f"bundle@{latest}"), deploy=fake_deploy,
                             start=fake_start, prune=calls["kept"].append, notify=calls["notify"].append):
        for name, state in states.items():
            if state is not None:
                watch.save(tmp / "sites" / name, state)
        code = watch.watch(enroll=enroll)
        saved = {folder.name: watch.load(folder) for folder in watch.sites()}
    return code, saved, calls["deploy"], calls["start"], len(calls["notify"]), calls["stop"], calls["kept"]


def scenario(state, latest, running=True, deploy_fails=False, rollback_fails=False, enroll=False, missing=()):
    """One poll of the owner's site alone: (exit code, saved state, deployed tags, rollback tags, notified, stops)."""
    tmp = Path(tempfile.mkdtemp())
    site(tmp, missing=missing)
    code, saved, deployed, started, notified, stops, _ = poll(
        tmp, {"owner": state}, latest, running=["owner"] if running else [], fail=["owner"] if deploy_fails else [],
        rollback_fails=rollback_fails, enroll="owner" if enroll else None)
    return code, saved["owner"], [t for _, t in deployed], [t for _, t in started], notified, stops


def test():
    good = {"current": "v0.1.0", "previous": None, "failed": []}
    # Not enrolled: never deploys on its own.
    assert scenario(None, "v0.1.0")[1:4] == (None, [], [])
    # Enrolling deploys the newest release and records it.
    assert scenario(None, "v0.1.0", enroll=True)[:3] == (0, {"current": "v0.1.0", "previous": None, "failed": []}, ["v0.1.0"])
    # Already on the newest release: nothing to do.
    assert scenario(good, "v0.1.0")[2] == []
    # Newer release: deployed and recorded, the old one kept as the previous release.
    assert scenario(good, "v0.2.0")[1] == {"current": "v0.2.0", "previous": "v0.1.0", "failed": []}
    # Newer release fails: rolled back to the last good one, marked failed, owner notified.
    code, saved, _, started, notified, stops = scenario(good, "v0.2.0", deploy_fails=True)
    assert (code, saved, started, notified, stops) == (1, good | {"failed": ["v0.2.0"]}, ["v0.1.0"], 1, 0)
    # A release that failed before is never retried automatically.
    assert scenario(good | {"failed": ["v0.2.0"]}, "v0.2.0")[2] == []
    # ...but enrolling retries it on purpose.
    assert scenario(good | {"failed": ["v0.2.0"]}, "v0.2.0", enroll=True)[2] == ["v0.2.0"]
    # Stack stopped by the owner: not started behind their back.
    assert scenario(good, "v0.2.0", running=False)[2] == []
    # Failed rollback is still recorded and notified.
    code, saved, _, _, notified, _ = scenario(good, "v0.2.0", deploy_fails=True, rollback_fails=True)
    assert (code, saved["failed"], notified) == (1, ["v0.2.0"], 1)
    # First deploy fails with nothing to roll back to: the stack is stopped (no crash loop) and the owner notified.
    code, saved, _, started, notified, stops = scenario(None, "v0.1.0", enroll=True, deploy_fails=True)
    assert (code, saved, started, notified, stops) == (1, {"current": None, "previous": None, "failed": ["v0.1.0"]}, [], 1, 1)
    # ...and a later release is still tried (stack was never running).
    assert scenario({"current": None, "previous": None, "failed": ["v0.1.0"]}, "v0.1.1", running=False)[2] == ["v0.1.1"]
    # No release published yet.
    assert scenario(good, None)[2] == []
    # Site config missing: nothing deployed (Docker would mount empty folders in its place), owner notified.
    code, saved, deployed, _, notified, _ = scenario(good, "v0.2.0", missing=[".env"])
    assert (code, deployed, notified) == (1, [], 1) and ".env" in saved["problem"]
    test_clients()
    test_registry_failure()
    test_tiers()
    test_layouts()
    test_check_bundle()
    test_latest_release()
    test_stage()
    test_prune()
    test_tag_images()
    test_heal_ports()
    test_stable()
    print("watch decisions ok (13 scenarios, 2 clients kept apart, layouts kept on rollback, registry failure notified once, images tagged, bundles checked "
          "and staged, old releases pruned, crash loops caught)")


def test_clients():
    """Two clients on one host (D-036): one's failure, rollback or stopped stack never touches the other."""
    good = {"current": "v0.1.0", "previous": "v0.0.9", "failed": []}
    tmp = Path(tempfile.mkdtemp())
    site(tmp, "owner"), site(tmp, "acme")
    assert (watch.project(tmp / "sites/owner"), watch.project(tmp / "sites/acme")) == ("cctv", "cctv-acme")
    # acme's deploy fails: only acme rolls back; the owner moves on, and cleanup keeps both clients' rollbacks.
    code, saved, deployed, started, notified, _, kept = poll(tmp, {"owner": good, "acme": good}, "v0.2.0",
                                                             running=["owner", "acme"], fail=["acme"])
    assert (code, notified, started) == (1, 1, [("acme", "v0.1.0")]), (code, notified, started)
    assert deployed == [("acme", "v0.2.0"), ("owner", "v0.2.0")], deployed
    assert saved["owner"] == {"current": "v0.2.0", "previous": "v0.1.0", "failed": []}
    assert saved["acme"] == good | {"failed": ["v0.2.0"]}
    assert kept == [{"v0.2.0", "v0.1.0", "v0.0.9"}], kept

    # The owner stopped its stack: only acme is deployed.
    tmp = Path(tempfile.mkdtemp())
    site(tmp, "owner"), site(tmp, "acme")
    deployed = poll(tmp, {"owner": good, "acme": good}, "v0.2.0", running=["acme"])[2]
    assert deployed == [("acme", "v0.2.0")], deployed

    # Enrolling one client deploys that client alone.
    tmp = Path(tempfile.mkdtemp())
    site(tmp, "owner"), site(tmp, "acme")
    deployed = poll(tmp, {"owner": good, "acme": None}, "v0.2.0", running=["owner"], enroll="acme")[2]
    assert deployed == [("acme", "v0.2.0")], deployed

    # A folder whose master.env names another client is refused: it would start a stack on that client's data.
    tmp = Path(tempfile.mkdtemp())
    site(tmp, "owner"), site(tmp, "acme", client="owner")
    code, saved, deployed, _, notified, _, _ = poll(tmp, {"owner": good, "acme": good}, "v0.2.0", running=["owner", "acme"])
    assert (code, deployed, notified) == (1, [("owner", "v0.2.0")], 1) and "CLIENT_ID='owner'" in saved["acme"]["problem"]

    # The smoke test asks this client's API port, read alone from its .env.
    (tmp / "sites/acme/.env").write_text("API_KEY=secret\nAPI_PORT=9190\n")
    assert watch.setting(tmp / "sites/acme/.env", "API_PORT", "9090") == "9190"
    assert watch.setting(tmp / "sites/owner/.env", "API_PORT", "9090") == "9090"


def test_tiers():
    """A client runs only a tier the release offers (D-041); a client with no tier file gets the base tier."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = site(Path(tmp))
        started = []
        offered = {"tiers": ["standard"]}
        with mock.patch.multiple(watch, stage=lambda tag, ref: offered, start=lambda tag, site: started.append(tag)):
            watch.deploy("v1", "bundle@v1", folder)
            (folder / "tier").write_text("deepstream\n")
            assert watch.tier(folder) == "deepstream"
            try:
                watch.deploy("v2", "bundle@v2", folder)
            except RuntimeError as e:
                assert "tier 'deepstream'" in str(e)
            else:
                raise AssertionError("a tier the release does not offer was started")
            offered["tiers"].append("deepstream")
            watch.deploy("v3", "bundle@v3", folder)
            del offered["tiers"]  # a bundle from before tiers offers the base tier only
            (folder / "tier").write_text("standard\n")
            watch.deploy("v4", "bundle@v4", folder)
        assert started == ["v1", "v3", "v4"], started


def test_layouts():
    """A site runs only its own layout's compose files (D-052), and a release without that layout is never started,
    rollback included: an edge site never falls back to the full stack, which would capture its cameras twice."""
    tmp = Path(tempfile.mkdtemp())
    releases = tmp / "releases"
    sample_bundle(releases / "v9.9.9", "v9.9.9")
    old = sample_bundle(releases / "v9.9.8", "v9.9.8")
    manifest = json.loads((old / "release-manifest.json").read_text())
    del manifest["layouts"]  # a bundle from before D-052
    (old / "release-manifest.json").write_text(json.dumps(manifest))
    folder = site(tmp)
    ups, smokes = [], []

    def fake_run(*cmd):
        if "up" in cmd:
            ups.append([Path(cmd[i + 1]).name for i, arg in enumerate(cmd) if arg == "-f"])
        return ""
    with mock.patch.multiple(watch, RELEASES=releases, run=fake_run, smoke=smokes.append, stable=lambda s: None,
                             tag_images=lambda tag: None):
        for layout, files in (("full", ["docker-compose-main.yml"]), ("central", ["docker-compose-main.yml", "docker-compose-central.yml"]),
                              ("edge", ["docker-compose-edge.yml"])):
            (folder / "layout").write_text(layout)
            assert watch.layout(folder) == layout
            watch.start("v9.9.9", folder)
            assert ups[-1] == files, (layout, ups[-1])
            assert all((releases / "v9.9.9" / name).is_file() for name in files)
        assert len(smokes) == 2, "the edge layout has no API to smoke-test"
        for layout in ("central", "edge"):
            (folder / "layout").write_text(layout)
            try:
                watch.start("v9.9.8", folder)
            except RuntimeError as e:
                assert f"layout {layout!r}" in str(e)
            else:
                raise AssertionError(f"a release without the {layout} layout was started")
        (folder / "layout").unlink()
        watch.start("v9.9.8", folder)  # no layout file: the full stack, which every bundle offers
        assert len(ups) == 4 and ups[-1] == ["docker-compose-main.yml"]


def test_registry_failure():
    """An expired registry token stops deploys: notify once, not every 10 minutes, and clear it once it works."""
    tmp = Path(tempfile.mkdtemp())
    folder = site(tmp)
    notified = []

    def failing():
        raise RuntimeError("docker pull failed: denied")

    with mock.patch.multiple(watch, SITES=tmp / "sites", LOG=tmp / "watch.log",
                             run=lambda *cmd: "", latest_release=failing, notify=notified.append):
        watch.save(folder, {"current": "v0.1.0", "previous": None, "failed": []})
        assert watch.watch() == 1 and watch.watch() == 1 and len(notified) == 1
        with mock.patch.object(watch, "latest_release", lambda: ("v0.1.0", "bundle@v0.1.0")):
            assert watch.watch() == 0
        assert "problem" not in watch.load(folder)


def sample_bundle(folder, tag="v9.9.9"):
    """A real bundle as make_bundle.py builds it in CI, with made-up digests."""
    env = (make_bundle.ROOT / "STANDALONE-SERVICES/standalone-services.env").read_text(encoding="utf-8")
    refs = make_bundle.app_images((make_bundle.ROOT / "docker-compose-main.yml").read_text(encoding="utf-8"), tag)
    refs.append(make_bundle.insightface_ref(env, "0" * 12))
    make_bundle.build(folder, tag, "deadbeef", {ref: f"sha256:{i:064x}" for i, ref in enumerate(refs, 1)})
    return folder


def refused(folder, tag):
    try:
        watch.check_bundle(folder, tag)
    except RuntimeError:
        return True
    return False


def test_check_bundle():
    """Only a bundle for this release, with our images pinned by digest, is accepted."""
    folder = sample_bundle(Path(tempfile.mkdtemp()) / "b")
    assert len(watch.check_bundle(folder, "v9.9.9")["images"]) == 9  # 8 app images + InsightFace
    assert refused(folder, "v1.0.0")
    manifest = folder / "release-manifest.json"
    good = manifest.read_text()
    for bad in (good.replace("@sha256:", ":latest#"), good.replace("ghcr.io/hamza-aziz-ai/", "ghcr.io/someone-else/")):
        manifest.write_text(bad)
        assert refused(folder, "v9.9.9")
    manifest.write_text(good)
    compose = folder / "docker-compose-main.yml"
    compose.write_text(compose.read_text() + "\n    build: .\n")
    assert refused(folder, "v9.9.9")


def test_latest_release():
    """The channel is pulled as the bundle's own platform on any host; a platform mismatch is an error, not "no release"."""
    pulls = []

    def fake_run(*cmd):
        if cmd[:2] == ("docker", "pull"):
            pulls.append(cmd)
            if fail:
                raise RuntimeError(fail)
        return "v9.9.9" if "inspect" in cmd and "{{index .Config" in cmd[3] else "bundle@sha256:1"
    with mock.patch.object(watch, "run", fake_run):
        fail = None
        assert watch.latest_release() == ("v9.9.9", "bundle@sha256:1")
        assert pulls[0][2:5] == ("-q", "--platform", "linux/amd64"), pulls[0]
        fail = "manifest unknown"
        assert watch.latest_release() is None
        fail = "no matching manifest for linux/arm64/v8 in the manifest list entries: not found"
        try:
            watch.latest_release()
        except RuntimeError:
            pass
        else:
            raise AssertionError("a platform mismatch was read as no release")


def test_stage():
    """The bundle is copied out of its image without running it; a bad one leaves nothing behind."""
    tmp = Path(tempfile.mkdtemp())
    source = sample_bundle(tmp / "image")
    calls = []

    def fake_run(*cmd):
        calls.append(cmd[:2])
        if cmd[:2] == ("docker", "create"):
            assert cmd[2:4] == ("--platform", "linux/amd64"), cmd  # an arm64 edge node copies the same amd64 bundle
        if cmd[:2] == ("docker", "cp"):
            shutil.copytree(source, cmd[3])
        return "container1" if cmd[:2] == ("docker", "create") else ""

    with mock.patch.multiple(watch, RELEASES=tmp / "releases", run=fake_run):
        watch.stage("v9.9.9", "bundle@sha256:1")
        assert (tmp / "releases/v9.9.9/docker-compose-main.yml").is_file()
        assert ("docker", "run") not in calls and ("docker", "rm") in calls
        try:
            watch.stage("v1.0.0", "bundle@sha256:2")  # the image holds v9.9.9's bundle: refused
        except RuntimeError:
            pass
        else:
            raise AssertionError("a bundle for another release was staged")
        assert sorted(p.name for p in (tmp / "releases").iterdir()) == ["v9.9.9"]


def test_prune():
    """Bundles and images of other releases go; the kept releases' images, dev builds and InsightFace stay."""
    tmp = Path(tempfile.mkdtemp())
    for tag in ("v9.9.9", "v9.9.8", "v9.9.7", "v9.9.6", "v9.9.5"):
        sample_bundle(tmp / "releases" / tag, tag)
    used = json.loads((tmp / "releases/v9.9.9/release-manifest.json").read_text())["images"]
    api = next(ref for ref in used.values() if "-api@" in ref)
    p = watch.IMAGE_PREFIX
    listed = [f"{api} id-kept", f"{p}api@sha256:{'f' * 64} id-old", f"{p}api@<none> id-dev",
              f"{p}insightface-rest@sha256:{'e' * 64} id-ifr", f"{p}deploy@sha256:{'d' * 64} id-bundle",
              f"{p}deploy@sha256:{'c' * 64} id-old-bundle", f"postgres@sha256:{'b' * 64} id-postgres"]
    removed = []

    def fake_run(*cmd):
        if cmd[:2] == ("docker", "ps"):
            return "abc123\ndef456"
        if cmd[:2] == ("docker", "inspect") and "Mounts" in cmd[3]:  # Docker Desktop reports both path styles
            return (r"/run/desktop/mnt/host/c/deploy/host/releases/v9.9.7/STANDALONE-SERVICES/Proxy/Caddyfile /data "
                    r"C:\deploy\host\releases\v9.9.6\STANDALONE-SERVICES\auth\milvus-user.yaml C:\deploy\host\proxy ")
        if cmd[:2] == ("docker", "inspect"):
            return f"{p}deploy@sha256:{'d' * 64}"
        if cmd[:2] == ("docker", "images"):
            return "\n".join(listed)
        removed.extend(cmd[3:])
        return ""

    with mock.patch.multiple(watch, RELEASES=tmp / "releases", run=fake_run, log=lambda msg: None):
        watch.prune({"v9.9.9", "v9.9.8"})
    # v9.9.5 goes; v9.9.6 and v9.9.7 stay because a running service mounts their files
    assert sorted(p.name for p in (tmp / "releases").iterdir()) == ["v9.9.6", "v9.9.7", "v9.9.8", "v9.9.9"]
    assert sorted(removed) == ["id-old", "id-old-bundle"], removed


def test_tag_images():
    """Every pinned image gets its name, its digest name goes only while a container uses it, and an image that is
    not on this host does not stop the rest."""
    tmp = Path(tempfile.mkdtemp())
    manifest = watch.check_bundle(sample_bundle(tmp / "v9.9.9"), "v9.9.9")
    tagged = []

    def fake_run(*cmd):
        if cmd[1] == "ps":
            return "" if cmd[-1].endswith("-roi:v9.9.9") else "abc123"
        if "insightface-rest" in cmd[2]:
            raise RuntimeError("No such image")
        tagged.append(cmd)
        return ""

    with mock.patch.multiple(watch, RELEASES=tmp, run=fake_run):
        watch.tag_images("v9.9.9")
    names = {cmd[3]: cmd[2] for cmd in tagged if cmd[1] == "tag"}
    removed = [cmd[3] for cmd in tagged if cmd[1] == "rmi"]
    assert all(cmd[1:3] == ("rmi", "-f") for cmd in tagged if cmd[1] != "tag")
    api = f"{watch.IMAGE_PREFIX}api:v9.9.9"
    assert names[api] in removed and tagged.index(("docker", "tag", names[api], api)) < tagged.index(("docker", "rmi", "-f", names[api]))
    assert names[f"{watch.IMAGE_PREFIX}roi:v9.9.9"] not in removed, "no container, so the image must stay"
    assert any(name.startswith("milvusdb/milvus:") for name in names), "standalone images are covered too"
    assert names[f"{watch.IMAGE_PREFIX}api:v9.9.9"] == manifest["images"][f"{watch.IMAGE_PREFIX}api:v9.9.9"]
    assert any(name.startswith("ghcr.io/hamza-aziz-ai/kafka-webapp:v") and "@sha256:" in pinned for name, pinned in names.items())
    assert not any("insightface-rest" in name for name in names)

    def fake_inspect(*cmd):
        tagged.append(cmd)
        return "v9.9.9"

    with mock.patch.object(watch, "run", fake_inspect):
        watch.latest_release()
    assert tagged[-1] == ("docker", "tag", watch.CHANNEL, f"{watch.CHANNEL.rsplit(':', 1)[0]}:v9.9.9")


def test_heal_ports():
    """A healthy container with a dead published port is restarted; one with live ports, or no port, is left alone."""
    calls = []
    listing = "aaa 0.0.0.0:9090->8000/tcp, [::]:9090->8000/tcp\nbbb 0.0.0.0:9095->9090/tcp\nccc "

    def fake_run(*cmd):
        calls.append(cmd)
        return listing if cmd[1] == "ps" else ""

    with mock.patch.multiple(watch, run=fake_run, log=lambda msg: None, port_answers=lambda port: port != "9090"):
        watch.heal_ports(Path("sites/owner"))
    assert ("docker", "restart", "aaa") in calls and len(calls) == 2, calls
    assert "health=healthy" in calls[0]
    calls.clear()
    with mock.patch.multiple(watch, run=fake_run, log=lambda msg: None, port_answers=lambda port: True):
        watch.heal_ports(Path("sites/owner"))
    assert len(calls) == 1, calls
    # An HTTP error still proves the port is live; a closed port does not
    with mock.patch.object(watch.urllib.request, "urlopen", side_effect=watch.urllib.error.HTTPError("u", 404, "no", {}, None)):
        assert watch.port_answers("1")
    with mock.patch.object(watch.urllib.request, "urlopen", side_effect=watch.http.client.RemoteDisconnected("empty")):
        assert not watch.port_answers("1")


def test_stable():
    """A crash-looping service fails the deploy even though the API answers."""
    with mock.patch.multiple(watch, STABLE_SECONDS=0, run=lambda *cmd: ""):
        watch.stable(Path("sites/owner"))
    with mock.patch.multiple(watch, STABLE_SECONDS=0, run=lambda *cmd: "mfr-cctv-producer-consumer"):
        try:
            watch.stable(Path("sites/owner"))
        except RuntimeError as e:
            assert "mfr-cctv-producer-consumer" in str(e)
        else:
            raise AssertionError("crash loop not detected")


if __name__ == "__main__":
    test()
