"""Starts automerge for green PRs it left open (#41 needed a manual start; D-029).

Developer tool, not part of the deployment bundle: it needs the owner's gh login, which deployment hosts never get.
Scheduled every 10 minutes on the owner's laptop from the dev checkout:
  pythonw deploy\\nudge_automerge.py         check once; log to deploy/nudge.log
  python  deploy\\nudge_automerge.py demo    self-check, needs no GitHub
"""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LOG = Path(__file__).resolve().parent / "nudge.log"
# A PR whose checks all passed this long ago, and is still open, was missed by automerge
STUCK_SECONDS = 15 * 60
GREEN = {"SUCCESS", "SKIPPED", "NEUTRAL"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def stuck_prs(prs, now):
    """Open PRs automerge should have merged: not drafts, no conflict, every check passed over STUCK_SECONDS ago."""
    def done(check):
        return datetime.fromisoformat(check["completedAt"].replace("Z", "+00:00")).timestamp()
    return [pr["number"] for pr in prs
            if not pr["isDraft"] and pr["mergeable"] != "CONFLICTING" and pr["statusCheckRollup"]
            and all(c.get("conclusion") in GREEN for c in pr["statusCheckRollup"])
            and now - max(done(c) for c in pr["statusCheckRollup"]) > STUCK_SECONDS]


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True, creationflags=NO_WINDOW).stdout


def nudge():
    try:
        prs = json.loads(gh("pr", "list", "--base", "main", "--json", "number,isDraft,mergeable,statusCheckRollup") or "[]")
        stuck = stuck_prs(prs, time.time())
        if stuck:
            gh("workflow", "run", "automerge.yml", "--ref", "main")
            msg = f"PRs {stuck} passed all checks over {STUCK_SECONDS // 60} min ago and are still open; started automerge"
        else:
            return
    except Exception as e:
        msg = f"Automerge check failed: {e}"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def demo():
    """Only a non-draft, non-conflicting PR whose checks all passed over 15 minutes ago counts as stuck."""
    now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc).timestamp()

    def pr(n, minutes_ago=20, conclusion="SUCCESS", draft=False, mergeable="MERGEABLE", checks=True):
        done = datetime.fromtimestamp(now - minutes_ago * 60, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rollup = [{"conclusion": "SUCCESS", "completedAt": "2026-10-31T11:00:00Z"},
                  {"conclusion": conclusion, "completedAt": done}] if checks else []
        return {"number": n, "isDraft": draft, "mergeable": mergeable, "statusCheckRollup": rollup}

    prs = [pr(1), pr(2, minutes_ago=5), pr(3, conclusion="FAILURE"), pr(4, conclusion=""), pr(5, draft=True),
           pr(6, mergeable="CONFLICTING"), pr(7, checks=False), pr(8, conclusion="SKIPPED")]
    assert stuck_prs(prs, now) == [1, 8], stuck_prs(prs, now)
    print("nudge ok (stuck PRs found; drafts, conflicts, failures and recent ones skipped)")


if __name__ == "__main__":
    demo() if sys.argv[1:] == ["demo"] else nudge()
