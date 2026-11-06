"""Renders every Mermaid diagram in the repository's Markdown with mermaid-cli and fails on any that does not parse, so a
broken diagram in README.md or docs/ is caught when it is pushed, not when someone opens the page. The diagrams are kept
by hand and updated in the same change as the code they describe; this checks that they still render, not that they are
still true.

Run: python3 -I deploy/check_diagrams.py
Needs Node's npx and Chrome: /usr/bin/google-chrome on GitHub's runners, the usual install path on Windows, or CHROME_PATH.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MMDC = ["npx", "-y", "@mermaid-js/mermaid-cli@11.17.1"]
CHROMES = [os.environ.get("CHROME_PATH"), "/usr/bin/google-chrome", "C:/Program Files/Google/Chrome/Application/chrome.exe"]
BLOCK = re.compile(r"```mermaid\r?\n(.*?)```", re.S)


def diagrams():
    """(file#n, source) for every Mermaid block in the tracked Markdown (submodules have their own checks)."""
    files = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    for name in files:
        if name.startswith("graphify-out/"):
            continue
        for number, source in enumerate(BLOCK.findall((ROOT / name).read_text(encoding="utf-8")), 1):
            yield f"{name}#{number}", source


def main():
    chrome = next((path for path in CHROMES if path and Path(path).exists()), None)
    if not chrome:
        sys.exit("No Chrome found: set CHROME_PATH")
    found = list(diagrams())
    failed = []
    with tempfile.TemporaryDirectory() as folder:
        config = Path(folder) / "puppeteer.json"
        # --no-sandbox: GitHub's Ubuntu runners refuse Chrome's sandbox to unprivileged processes
        config.write_text(json.dumps({"executablePath": chrome, "args": ["--no-sandbox"]}), encoding="utf-8")
        for index, (where, source) in enumerate(found):
            diagram = Path(folder) / f"{index}.mmd"
            diagram.write_text(source, encoding="utf-8")
            result = subprocess.run([*MMDC, "-p", str(config), "-i", str(diagram), "-o", str(diagram.with_suffix(".svg"))],
                                    capture_output=True, text=True, shell=os.name == "nt")
            if result.returncode:
                error = next((line for line in result.stderr.splitlines() if "Error" in line), result.stderr.strip()[-300:])
                failed.append(f"{where}: {error}")
    for line in failed:
        print(f"::error::{line}" if os.environ.get("GITHUB_ACTIONS") else line)
    if failed:
        sys.exit(f"{len(failed)} of {len(found)} diagrams do not render")
    print(f"diagrams ok ({len(found)} rendered)")


if __name__ == "__main__":
    main()
