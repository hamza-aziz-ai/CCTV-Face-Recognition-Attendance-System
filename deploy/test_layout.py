"""Two clients' stacks on one host share nothing that collides (D-036 step 2): no fixed container names, different
published ports, every data path inside the client's own site folder, and internal services reached by service name
on the project's own network instead of a published port. Needs Docker Compose, no running containers.
Run from the repo root: python3 -I deploy/test_layout.py"""
import ast
import json
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "docker-compose-main.yml"
CLIENTS = {
    "cctv": {},  # the owner: today's ports
    "cctv-acme": {"API_PORT": "9190", "DISPLAY_IMAGE_PORT": "20113", "DISPLAY_PORT": "9195"},  # set in acme's site .env
}


def render(project, site, ports):
    env = {k: v for k, v in os.environ.items() if k not in ("API_PORT", "DISPLAY_IMAGE_PORT", "DISPLAY_PORT")} | ports
    out = subprocess.run(["docker", "compose", "-p", project, "--project-directory", str(site), "-f", str(COMPOSE),
                          "config", "--format", "json"], env=env, capture_output=True, text=True, check=True).stdout
    return json.loads(out)["services"]


def internal_hosts():
    """The services that src/parameters.py reaches by name."""
    values = {node.targets[0].id: node.value.value for node in ast.parse((ROOT / "src/parameters.py").read_text(encoding="utf-8")).body
              if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Constant)}
    return {values["DATABASE_HOST"], values["FEEDBACK_HOST"], urlparse(values["DYNAMIC_FACE_DATA_COLLECTOR_API"]).hostname}


def test():
    published = {}
    with tempfile.TemporaryDirectory() as tmp:
        for project, ports in CLIENTS.items():
            site = Path(tmp, project).resolve()
            site.mkdir()
            services = render(project, site, ports)
            assert not [name for name, s in services.items() if "container_name" in s], "fixed container names"
            assert not [name for name in services if "postgres" in name], "PostgreSQL is shared, not per client"
            published[project] = {int(p["published"]) for s in services.values() for p in s.get("ports", [])}
            for name, service in services.items():
                for volume in service.get("volumes", []):
                    if volume["type"] == "bind":
                        assert Path(volume["source"]).resolve().is_relative_to(site), (project, name, volume["source"])
            for host in internal_hosts():
                assert host in services and not services[host].get("ports"), (host, "must be a service, not published")
    assert published["cctv"] == {9090, 20013, 9095}, published["cctv"]
    assert not published["cctv"] & published["cctv-acme"], published
    print(f"layout ok ({len(CLIENTS)} clients: no container names, own ports, data in own site folder, "
          f"{len(internal_hosts())} internal services by name)")


if __name__ == "__main__":
    test()
