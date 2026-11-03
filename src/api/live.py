"""Live view (8b, D-047): each camera's video passed through this client's MediaMTX as HLS, beside its latest
recognitions. The API writes MediaMTX's configuration from the camera configuration at start, and serves the page and
its data. Video reaches the browser only through the proxy's /live/ route, behind the same sign-in (D-040).
"""
import json
import os
import re
import sys
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

current = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.dirname(current))
import accounts  # noqa: E402
from custom_logging import api_logger  # noqa: E402
from parameters import CAMERA_CONFIGURATION_FILE  # noqa: E402
from util.generic_utilities import camera_stream_url  # noqa: E402

# Live video of people is for the client's administrators and viewers, not enrolment staff (owner, 2026-11-03)
LIVE_ROLES = ("client_admin", "viewer")
live_viewer = accounts.require(*LIVE_ROLES)
CONFIG_PATH = os.getenv("LIVE_VIDEO_CONFIG", "/live-video/mediamtx.yml")
PAGE = open(os.path.join(current, "live.html"), encoding="utf-8").read()

router = APIRouter(prefix="/live")


def setup(get_cursor: Callable):
    global cursor_source
    cursor_source = get_cursor


def cameras() -> dict:
    """Camera name to its stream URL, named as the producer names them. HTTP cameras are left out: MediaMTX pulls RTSP."""
    with open(CAMERA_CONFIGURATION_FILE, "r") as file:
        configuration = json.load(file)
    found = {}
    for location, points in configuration.items():
        for point, cctv_cameras in (points.get("cctv-cameras") or {}).items():
            for cctv_camera, camera_config in (cctv_cameras or {}).items():
                if not (camera_config or {}).get("ip_address"):
                    continue  # an unfinished entry: the producer cannot open it either
                url = camera_stream_url(camera_config)
                if url.startswith("rtsp://"):
                    found[f"{location}_{point}_{cctv_camera}"] = url
    return found


def path_name(camera: str) -> str:
    """A MediaMTX path (and URL segment) for a camera name."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", camera)


def mediamtx_config(streams: dict) -> str:
    """HLS only, nothing published or served in any other protocol. Each camera is pulled over TCP only while someone
    watches it, so cameras carry no extra stream otherwise. JSON strings are valid YAML, which quotes the URLs safely."""
    lines = ["logLevel: warn", "api: no", "metrics: no", "pprof: no", "playback: no",
             "rtsp: no", "rtmp: no", "webrtc: no", "srt: no", "moq: no",
             "hls: yes", "hlsAddress: :8888", "hlsVariant: lowLatency", "paths:"]
    for camera, url in sorted(streams.items()):
        # Named under live/, the URL prefix the proxy routes here unchanged, so MediaMTX's own redirects (its
        # cookie check) keep the prefix
        lines += [f"  live/{path_name(camera)}:", f"    source: {json.dumps(url)}", "    sourceOnDemand: yes",
                  "    rtspTransport: tcp"]
    if not streams:
        lines[-1] = "paths: {}"
    return "\n".join(lines) + "\n"


def write_config(path: str = CONFIG_PATH) -> int:
    """Writes MediaMTX's configuration, which holds camera passwords, readable by its owner only. MediaMTX reloads it
    when it changes. Returns the number of cameras."""
    try:
        streams = cameras()
    except Exception as error:
        api_logger.error(f"Live view: cannot read the camera configuration: {error}")
        streams = {}
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        api_logger.warning(f"Live view: {folder} is not mounted, so no live video")
        return 0
    temporary = f"{path}.tmp"
    with open(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as file:
        file.write(mediamtx_config(streams))
    os.replace(temporary, path)
    api_logger.info(f"Live view: MediaMTX configured for {len(streams)} cameras")
    return len(streams)


@router.get("", response_class=HTMLResponse)
def page(request: Request):
    caller = accounts.identify(request)
    if caller is None:
        return RedirectResponse("/auth/sign-in")
    if caller["role"] not in LIVE_ROLES:
        raise HTTPException(status_code=403, detail="Your role does not allow this")
    return PAGE


@router.get("/check", status_code=204)
def check(caller: dict = Depends(live_viewer)):
    """For the proxy's /live/ route: 204 lets a viewer through to the video, 401 sends them to sign in, 403 refuses."""


@router.get("/cameras")
def camera_list(caller: dict = Depends(live_viewer)):
    return [{"name": camera, "path": path_name(camera)} for camera in sorted(cameras())]


@router.get("/events")
def events(per_camera: int = 10, caller: dict = Depends(live_viewer)):
    """Each camera's latest recognitions from today and yesterday: name, date, time and score, no images."""
    per_camera = max(1, min(per_camera, 50))
    with cursor_source(commit=False) as cursor:
        cursor.execute("""
            SELECT person_id, camera_name, recognition_date, recognition_time, confidence_score FROM (
                SELECT person_id, camera_name, recognition_date, recognition_time, confidence_score,
                       row_number() OVER (PARTITION BY camera_name ORDER BY recognition_date DESC, recognition_time DESC) AS n
                FROM recognition_results WHERE recognition_date >= CURRENT_DATE - 1) latest
            WHERE n <= %s ORDER BY camera_name, n""", (per_camera,))
        rows = cursor.fetchall()
    grouped = {}
    for row in rows:
        grouped.setdefault(row["camera_name"], []).append({
            "person_id": row["person_id"], "date": str(row["recognition_date"]), "time": str(row["recognition_time"]),
            "score": None if row["confidence_score"] is None else round(float(row["confidence_score"]), 3)})
    return grouped


if __name__ == "__main__":
    print(f"MediaMTX configured for {write_config()} cameras")  # never prints the file: it holds camera passwords
