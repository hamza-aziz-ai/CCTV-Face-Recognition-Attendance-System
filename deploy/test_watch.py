"""Decision tests for deploy/watch.py with Docker, git and GitHub faked out. Run: python -I deploy/test_watch.py"""
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import watch  # noqa: E402


def scenario(state, latest, running=True, deploy_fails=False, rollback_fails=False, enroll=False):
    """Run one poll and return (exit code, saved state, deployed tags, started-for-rollback tags, notified)."""
    tmp = Path(tempfile.mkdtemp())
    calls = {"deploy": [], "start": [], "notify": []}

    def fake_run(*cmd, env=None):
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
    return code, saved, calls["deploy"], calls["start"], len(calls["notify"])


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
    code, saved, _, started, notified = scenario({"current": "v0.1.0", "failed": []}, "v0.2.0", deploy_fails=True)
    assert (code, saved, started, notified) == (1, {"current": "v0.1.0", "failed": ["v0.2.0"]}, ["v0.1.0"], 1)
    # A release that failed before is never retried automatically.
    assert scenario({"current": "v0.1.0", "failed": ["v0.2.0"]}, "v0.2.0")[2] == []
    # ...but enrolling retries it on purpose.
    assert scenario({"current": "v0.1.0", "failed": ["v0.2.0"]}, "v0.2.0", enroll=True)[2] == ["v0.2.0"]
    # Stack stopped by the owner: not started behind their back.
    assert scenario({"current": "v0.1.0", "failed": []}, "v0.2.0", running=False)[2] == []
    # Failed rollback is still recorded and notified.
    code, saved, _, _, notified = scenario({"current": "v0.1.0", "failed": []}, "v0.2.0", deploy_fails=True, rollback_fails=True)
    assert (code, saved["failed"], notified) == (1, ["v0.2.0"], 1)
    # First deploy fails with nothing to roll back to; a later release is still tried (stack was never running).
    assert scenario({"current": None, "failed": ["v0.1.0"]}, "v0.1.1", running=False)[2] == ["v0.1.1"]
    # No release published yet.
    assert scenario({"current": None, "failed": []}, None)[2] == []
    print("watch decisions ok (11 scenarios)")


if __name__ == "__main__":
    test()
