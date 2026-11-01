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


def site(root, missing=()):
    for name in watch.SITE_FILES:
        if name not in missing:
            (root / "site" / name).parent.mkdir(parents=True, exist_ok=True)
            (root / "site" / name).write_text("x")


def scenario(state, latest, running=True, deploy_fails=False, rollback_fails=False, enroll=False, missing=()):
    """Run one poll and return (exit code, saved state, deployed tags, started-for-rollback tags, notified, stack stops)."""
    tmp = Path(tempfile.mkdtemp())
    site(tmp, missing)
    calls = {"deploy": [], "start": [], "notify": [], "stop": 0}

    def fake_run(*cmd):
        calls["stop"] += cmd[:2] == ("docker", "stop")
        return "abc123" if running and "status=running" in cmd else ""

    def fake_deploy(tag, ref):
        assert ref == f"bundle@{tag}"
        calls["deploy"].append(tag)
        if deploy_fails:
            raise RuntimeError("up failed")

    def fake_start(tag):
        calls["start"].append(tag)
        if rollback_fails:
            raise RuntimeError("rollback failed")

    with mock.patch.multiple(watch, STATE=tmp / "state.json", LOG=tmp / "watch.log", SITE=tmp / "site", run=fake_run,
                             latest_release=lambda: latest and (latest, f"bundle@{latest}"), deploy=fake_deploy,
                             start=fake_start, prune=lambda keep: None, notify=calls["notify"].append):
        if state is not None:
            watch.save(state)
        code = watch.watch(enroll=enroll)
        saved = json.loads((tmp / "state.json").read_text()) if (tmp / "state.json").exists() else None
    return code, saved, calls["deploy"], calls["start"], len(calls["notify"]), calls["stop"]


def test():
    # Not enrolled: never deploys on its own.
    assert scenario(None, "v0.1.0")[1:4] == (None, [], [])
    # Enrolling deploys the newest release and records it.
    assert scenario(None, "v0.1.0", enroll=True)[:3] == (0, {"current": "v0.1.0", "failed": []}, ["v0.1.0"])
    # Already on the newest release: nothing to do.
    assert scenario({"current": "v0.1.0", "failed": []}, "v0.1.0")[2] == []
    # Newer release: deployed and recorded.
    assert scenario({"current": "v0.1.0", "failed": []}, "v0.2.0")[1] == {"current": "v0.2.0", "failed": []}
    # Newer release fails: rolled back to the last good one, marked failed, owner notified.
    code, saved, _, started, notified, stops = scenario({"current": "v0.1.0", "failed": []}, "v0.2.0", deploy_fails=True)
    assert (code, saved, started, notified, stops) == (1, {"current": "v0.1.0", "failed": ["v0.2.0"]}, ["v0.1.0"], 1, 0)
    # A release that failed before is never retried automatically.
    assert scenario({"current": "v0.1.0", "failed": ["v0.2.0"]}, "v0.2.0")[2] == []
    # ...but enrolling retries it on purpose.
    assert scenario({"current": "v0.1.0", "failed": ["v0.2.0"]}, "v0.2.0", enroll=True)[2] == ["v0.2.0"]
    # Stack stopped by the owner: not started behind their back.
    assert scenario({"current": "v0.1.0", "failed": []}, "v0.2.0", running=False)[2] == []
    # Failed rollback is still recorded and notified.
    code, saved, _, _, notified, _ = scenario({"current": "v0.1.0", "failed": []}, "v0.2.0", deploy_fails=True, rollback_fails=True)
    assert (code, saved["failed"], notified) == (1, ["v0.2.0"], 1)
    # First deploy fails with nothing to roll back to: the stack is stopped (no crash loop) and the owner notified.
    code, saved, _, started, notified, stops = scenario(None, "v0.1.0", enroll=True, deploy_fails=True)
    assert (code, saved, started, notified, stops) == (1, {"current": None, "failed": ["v0.1.0"]}, [], 1, 1)
    # ...and a later release is still tried (stack was never running).
    assert scenario({"current": None, "failed": ["v0.1.0"]}, "v0.1.1", running=False)[2] == ["v0.1.1"]
    # No release published yet.
    assert scenario({"current": None, "failed": []}, None)[2] == []
    # Site config missing: nothing deployed (Docker would mount empty folders in its place), owner notified.
    code, saved, deployed, _, notified, _ = scenario({"current": "v0.1.0", "failed": []}, "v0.2.0", missing=[".env"])
    assert (code, deployed, notified) == (1, [], 1) and ".env" in saved["problem"]
    test_registry_failure()
    test_check_bundle()
    test_stage()
    test_prune()
    test_stable()
    print("watch decisions ok (13 scenarios, registry failure notified once, bundles checked and staged, "
          "old releases pruned, crash loops caught)")


def test_registry_failure():
    """An expired registry token stops deploys: notify once, not every 10 minutes, and clear it once it works."""
    tmp = Path(tempfile.mkdtemp())
    site(tmp)
    notified = []

    def failing():
        raise RuntimeError("docker pull failed: denied")

    with mock.patch.multiple(watch, STATE=tmp / "state.json", LOG=tmp / "watch.log", SITE=tmp / "site",
                             run=lambda *cmd: "", latest_release=failing, notify=notified.append):
        watch.save({"current": "v0.1.0", "failed": []})
        assert watch.watch() == 1 and watch.watch() == 1 and len(notified) == 1
        with mock.patch.object(watch, "latest_release", lambda: ("v0.1.0", "bundle@v0.1.0")):
            assert watch.watch() == 0
        assert "problem" not in json.loads((tmp / "state.json").read_text())


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
    assert len(watch.check_bundle(folder, "v9.9.9")["images"]) == 8
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


def test_stage():
    """The bundle is copied out of its image without running it; a bad one leaves nothing behind."""
    tmp = Path(tempfile.mkdtemp())
    source = sample_bundle(tmp / "image")
    calls = []

    def fake_run(*cmd):
        calls.append(cmd[:2])
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
    for tag in ("v9.9.9", "v9.9.8", "v9.9.7"):
        sample_bundle(tmp / "releases" / tag, tag)
    used = json.loads((tmp / "releases/v9.9.9/release-manifest.json").read_text())["images"]
    api = next(ref for ref in used.values() if "-api@" in ref)
    p = watch.IMAGE_PREFIX
    listed = [f"{api} id-kept", f"{p}api@sha256:{'f' * 64} id-old", f"{p}api@<none> id-dev",
              f"{p}insightface-rest@sha256:{'e' * 64} id-ifr", f"{p}deploy@sha256:{'d' * 64} id-bundle",
              f"{p}deploy@sha256:{'c' * 64} id-old-bundle", f"postgres@sha256:{'b' * 64} id-postgres"]
    removed = []

    def fake_run(*cmd):
        if cmd[:2] == ("docker", "inspect"):
            return f"{p}deploy@sha256:{'d' * 64}"
        if cmd[:2] == ("docker", "images"):
            return "\n".join(listed)
        removed.extend(cmd[3:])
        return ""

    with mock.patch.multiple(watch, RELEASES=tmp / "releases", run=fake_run, log=lambda msg: None):
        watch.prune({"v9.9.9", "v9.9.8"})
    assert sorted(p.name for p in (tmp / "releases").iterdir()) == ["v9.9.8", "v9.9.9"]
    assert sorted(removed) == ["id-old", "id-old-bundle"], removed


def test_stable():
    """A crash-looping service fails the deploy even though the API answers."""
    with mock.patch.multiple(watch, STABLE_SECONDS=0, run=lambda *cmd: ""):
        watch.stable()
    with mock.patch.multiple(watch, STABLE_SECONDS=0, run=lambda *cmd: "mfr-cctv-producer-consumer"):
        try:
            watch.stable()
        except RuntimeError as e:
            assert "mfr-cctv-producer-consumer" in str(e)
        else:
            raise AssertionError("crash loop not detected")


if __name__ == "__main__":
    test()
