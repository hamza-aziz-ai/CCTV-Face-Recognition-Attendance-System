"""Decision tests for deploy/watch.py with Docker, git and GitHub faked out. Run: python -I deploy/test_watch.py"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import watch  # noqa: E402


def scenario(state, latest, running=True, deploy_fails=False, rollback_fails=False, enroll=False):
    """Run one poll and return (exit code, saved state, deployed tags, started-for-rollback tags, notified, stack stops)."""
    tmp = Path(tempfile.mkdtemp())
    calls = {"deploy": [], "start": [], "notify": [], "stop": 0}

    def fake_run(*cmd, env=None):
        calls["stop"] += cmd[-1] == "stop"
        return "abc123" if running and cmd[-2:] == ("ps", "-q") else ""

    def fake_deploy(tag):
        calls["deploy"].append(tag)
        if deploy_fails:
            raise RuntimeError("up failed")

    def fake_start(tag):
        calls["start"].append(tag)
        if rollback_fails:
            raise RuntimeError("rollback failed")

    with mock.patch.multiple(watch, STATE=tmp / "state.json", LOG=tmp / "watch.log", run=fake_run,
                             latest_release=lambda: latest, deploy=fake_deploy, start=fake_start,
                             notify=calls["notify"].append):
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
    test_site_config_survives_checkout()
    test_prune()
    test_stable()
    print("watch decisions ok (12 scenarios, site config kept, old images pruned, crash loops caught)")


def test_stable():
    """A crash-looping service fails the deploy even though the API answers."""
    with mock.patch.multiple(watch, STABLE_SECONDS=0, run=lambda *cmd, env=None: ""):
        watch.stable()
    with mock.patch.multiple(watch, STABLE_SECONDS=0, run=lambda *cmd, env=None: "mfr-cctv-producer-consumer"):
        try:
            watch.stable()
        except RuntimeError as e:
            assert "mfr-cctv-producer-consumer" in str(e)
        else:
            raise AssertionError("crash loop not detected")


def test_prune():
    """Only release images of other tags go: not the kept tags, dev builds or other images."""
    p = watch.IMAGE_PREFIX
    listed = [f"{p}api:v1.0.0", f"{p}api:v2.0.0", f"{p}api:v0.9.0", f"{p}api:v-beta", "postgres:18.6-trixie"]
    removed = []

    def fake_run(*cmd, env=None):
        if cmd[1] == "images":
            return "\n".join(listed)
        removed.extend(cmd[2:])
        return ""

    with mock.patch.multiple(watch, run=fake_run, log=lambda msg: None):
        watch.prune({"v2.0.0", "v1.0.0"})
    assert removed == [f"{p}api:v0.9.0"], removed


def test_site_config_survives_checkout():
    """start() with real git: master.env is tracked at v1, untracked at v2; the host's copy survives both ways."""
    repo = Path(tempfile.mkdtemp())
    git = lambda *a: subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a],  # noqa: E731
                                    check=True, capture_output=True)
    git("init", "-q")
    (repo / "master.env").write_text("SETTING=REPO\n")
    git("add", "master.env")
    git("commit", "-q", "-m", "v1")
    git("tag", "v1")
    git("rm", "-q", "--cached", "master.env")
    git("commit", "-q", "-m", "v2")
    git("tag", "v2")
    (repo / "master.env").write_text("SETTING=SITE\n")
    real_run = watch.run
    with mock.patch.multiple(watch, ROOT=repo, smoke=lambda: None, STABLE_SECONDS=0,
                             run=lambda *cmd, env=None: real_run(*cmd) if cmd[0] == "git" else ""):
        for tag in ("v1", "v2", "v1"):
            watch.start(tag)
            assert (repo / "master.env").read_text() == "SETTING=SITE\n", tag


if __name__ == "__main__":
    test()
