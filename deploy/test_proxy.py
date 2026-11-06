"""The HTTPS route of deploy/provision.py on a real Caddy, with stand-ins for the API and display: signed-out visitors go to the sign-in page, the API's docs stay closed, and live video reaches only roles allowed to watch. Needs Docker. Run: python3 -I deploy/test_proxy.py"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy"))
import provision  # noqa: E402

IMAGE = "caddy:2.10-alpine"
NETWORK = "proxytest"
PORT = "18443"
HOST = "acme.localhost"
API = """:8000 {
	@signed_in header Cookie *good*
	@operator header Cookie *operator*
	handle /auth/check {
		respond @signed_in 204
		respond @operator 204
		respond 401
	}
	handle /live/check {
		respond @signed_in 204
		respond @operator 403
		respond 401
	}
	respond "api {path}" 200
}
"""
DISPLAY = """:9090 {
	respond "display {path}" 200
}
"""
LIVE = """:8888 {
	respond "live {path}" 200
}
"""
HEALTH = """:20010 {
	respond "health {path}" 200
}
"""
ROI = """:8069 {
	respond "roi {path}" 200
}
"""


def docker(*args, check=True):
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check)


def stand_in(name, config, folder):
    path = Path(folder) / f"{name}.Caddyfile"
    path.write_text(config, encoding="utf-8")
    docker("run", "-d", "--name", name, "--network", NETWORK, "-v", f"{path}:/etc/caddy/Caddyfile:ro", IMAGE)


def fetch(path, cookie=None, *extra):
    """(status, redirect target, body), through the proxy, with the private CA unchecked."""
    command = ["curl", "-sk", "-m", "8", "--resolve", f"{HOST}:{PORT}:127.0.0.1", "-w", "\n%{http_code} %{redirect_url}", *extra]
    if cookie:
        command += ["-H", f"Cookie: {cookie}"]
    out = subprocess.run([*command, f"https://{HOST}:{PORT}{path}"], capture_output=True, text=True).stdout
    body, _, tail = out.rpartition("\n")
    status, _, redirect = tail.partition(" ")
    return status, redirect, body


def test():
    assert "cctv-mfr-api-service-1:8000" in provision.proxy_route("owner", "owner.localhost")
    assert "collector" not in provision.proxy_route("owner", "owner.localhost"), "the collector is reached only through the API"
    # An edge node captures (D-052): /health follows its readiness, and nothing but http://host:port/health goes into the file
    assert provision.edge_health(None) is None
    assert provision.edge_health("http://10.0.0.9:20010/health") == "10.0.0.9:20010"
    assert "reverse_proxy 10.0.0.9:20010" in provision.proxy_route("owner", "owner.localhost", "10.0.0.9:20010")
    for bad in ("https://10.0.0.9:20010/health", "http://10.0.0.9/health", "http://10.0.0.9:20010/x", "http://a{b}:1/health"):
        try:
            provision.edge_health(bad)
            raise AssertionError(f"accepted {bad}")
        except provision.Stop:
            pass
    with tempfile.TemporaryDirectory(dir=os.environ.get("RUNNER_TEMP")) as folder:
        sites = Path(folder) / "sites"
        (sites / "acme").mkdir(parents=True)
        (sites / "acme" / ".env").write_text(f"SITE_HOST={HOST}\n", encoding="utf-8")
        assert provision.write_proxy_route("acme", sites) == HOST
        # The edge's .env: its own logins and the camera login, never central-only keys
        (sites / "acme" / ".env").write_text(f"SITE_HOST={HOST}\nPG_APP_USER=acme_app\nPG_APP_PASSWORD=p1\nCAM_PASSWORD=c\n"
                                             "KAFKA_DISPLAY_PASSWORD=d\nSTORE_APP_SECRET_KEY=s\nPOSTGRES_PASSWORD=admin\n", encoding="utf-8")
        edge = provision.read_env(provision.write_edge_env("acme", sites))
        assert edge == {"CAM_PASSWORD": "c", "PG_APP_USER": "acme_app", "PG_APP_PASSWORD": "p1"}, edge
        (sites / "evil").mkdir()
        (sites / "evil" / ".env").write_text("SITE_HOST=x { respond hacked }\n", encoding="utf-8")
        try:
            provision.write_proxy_route("evil", sites)
        except provision.Stop:
            pass
        else:
            raise AssertionError("a host name with Caddy syntax was accepted")
        names = ("cctv-acme-mfr-api-service-1", "cctv-acme-kafka-webapp-1", "cctv-acme-live-video-1", "proxytest-caddy", "cctv-acme-mfr-cctv-producer-consumer-1",
                 "cctv-acme-roi-provisioning-1")
        docker("network", "create", NETWORK)
        try:
            stand_in(names[0], API, folder)
            stand_in(names[1], DISPLAY, folder)
            stand_in(names[2], LIVE, folder)
            stand_in(names[4], HEALTH, folder)
            stand_in(names[5], ROI, folder)
            docker("run", "-d", "--name", names[3], "--network", NETWORK, "-p", f"127.0.0.1:{PORT}:443", "-v", f"{ROOT / 'STANDALONE-SERVICES/Proxy/Caddyfile'}:/etc/caddy/Caddyfile:ro", "-v", f"{sites.parent / 'proxy'}:/routes:ro", IMAGE)
            for _ in range(40):
                if fetch("/auth/sign-in")[0] == "200":
                    break
                time.sleep(0.5)
            status, redirect, _ = fetch("/")
            assert status == "302" and redirect.endswith("/auth/sign-in"), (status, redirect)
            assert fetch("/socket.io/?EIO=4")[0] == "302"
            assert fetch("/", "session=bad")[0] == "302"
            assert fetch("/", "session=good")[::2] == ("200", "display /")
            socket = fetch("/socket.io/", "session=good", "-H", "Connection: Upgrade", "-H", "Upgrade: websocket", "--http1.1")
            assert socket[0] == "200" and socket[2].startswith("display"), socket
            assert fetch("/auth/sign-in")[::2] == ("200", "api /auth/sign-in")
            assert fetch("/static/fonts/x.ttf")[::2] == ("200", "display /static/fonts/x.ttf"), "the sign-in page needs its fonts before sign-in"
            assert fetch("/static/other.js")[0] == "302"
            assert fetch("/api/fetch_module_data")[::2] == ("200", "api /fetch_module_data")
            for closed in ("/api/docs", "/api/redoc", "/api/openapi.json"):
                assert fetch(closed)[0] == "404", closed
            assert fetch("/docs")[0] == "302"
            # Live video (D-047): signed-out visitors go to sign-in, enrolment staff are refused, viewers reach MediaMTX
            live = fetch("/live/maingate_entry_cctv-camera-1/index.m3u8")
            assert live[0] == "302" and live[1].endswith("/auth/sign-in"), live
            assert fetch("/live/maingate_entry_cctv-camera-1/", "session=operator")[0] == "403"
            assert fetch("/live/maingate_entry_cctv-camera-1/", "session=good")[::2] == ("200", "live /live/maingate_entry_cctv-camera-1/")
            # Readiness for displays outside the stack needs no session, and only /health itself is open (D-051)
            assert fetch("/health")[::2] == ("200", "health /health")
            assert fetch("/health/x")[0] == "302"
            # The camera region page (D-035 addendum): /roi/* reaches the ROI app with the prefix stripped, signed in or
            # not, because the app asks the API about every request itself; /roi alone is sent to /roi/
            assert fetch("/roi/api/cameras")[::2] == ("200", "roi /api/cameras")
            assert fetch("/roi/")[::2] == ("200", "roi /")
            roi = fetch("/roi")
            assert roi[0] in ("301", "302", "308") and roi[1].endswith("/roi/"), roi
        finally:
            docker("rm", "-f", *names, check=False)
            docker("network", "rm", NETWORK, check=False)
    print("proxy ok (signed-out visitors sent to sign-in, display and WebSockets need a session, API routes reachable, API docs closed, live video for viewers only, readiness open at /health only, region page routed to its app, bad host names refused)")


if __name__ == "__main__":
    test()
