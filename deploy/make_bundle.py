"""Builds the deployment bundle: the only files a deployment host gets from this repository (D-033).

A host needs compose files, ops scripts, config templates and licences, never the source code, which lives only in the
images. The bundle keeps the repository's folder layout, so the scripts work unchanged. Image references are pinned to
the digests published for the release, because a tag can be pushed twice (it happened to v2.0.2).

Usage: python3 -I deploy/make_bundle.py <out dir> <release tag> <commit> <digests.json>
         digests.json maps each image reference by tag (as published) to its sha256 digest
       python3 -I deploy/make_bundle.py demo [dir]  self-check, needs no Docker; with dir, also leaves a sample bundle there
"""
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    "docker-compose-main.yml",
    "STANDALONE-SERVICES/standalone-services.env",
    "STANDALONE-SERVICES/Confluent-Kafka/docker-compose.yml",
    "STANDALONE-SERVICES/Milvus-Vector-Database/docker-compose.yml",
    "STANDALONE-SERVICES/Dataset-Store/docker-compose.yml",
    "STANDALONE-SERVICES/InsightFace-REST/deploy_trt_multi-gpu.sh",
    "STANDALONE-SERVICES/InsightFace-REST/misc/nginx_conf/conf.d/default.conf",
    "STANDALONE-SERVICES/InsightFace-REST/models/models.json",
    "STANDALONE-SERVICES/InsightFace-REST/LICENSE",
    "start_standalone_services.sh",
    "stop_standalone_services.sh",
    "set_configuration.sh",
    "get_ip.sh",
    "master.env.example",
    ".env.example",
    "src/Camera-Configuration/camera_configuration.example.json",
]
APP_IMAGE = re.compile(r"(ghcr\.io/hamza-aziz-ai/cctv-face-recognition-[a-z-]+):\$\{IMAGE_TAG:-v-beta\}")
SCHEMA = 1


def app_images(compose_text, tag):
    """The app image references of a release, by tag, as the release workflow publishes them."""
    return sorted({f"{name}:{tag}" for name in APP_IMAGE.findall(compose_text)})


def insightface_ref(env_text, tree):
    image = re.search(r"^IMAGE='([^']+)'", env_text, re.M).group(1)
    version = re.search(r"^TAG='([^']+)'", env_text, re.M).group(1)
    return f"{image}:{version}-{tree}"


def build(out, tag, commit, digests, root=ROOT):
    """Copy the allow-listed files to out, pin every app and InsightFace image to its digest, write the manifest."""
    out = Path(out)
    for name in FILES:
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, out / name)
    pinned = {}
    for ref, digest in digests.items():
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            sys.exit(f"{ref}: not a digest: {digest}")
        pinned[ref] = f"{ref.rsplit(':', 1)[0]}@{digest}"
    compose = out / "docker-compose-main.yml"
    text = compose.read_text(encoding="utf-8")
    missing = [ref for ref in app_images(text, tag) if ref not in pinned]
    if missing:
        sys.exit(f"No digest for {missing}")
    compose.write_text(APP_IMAGE.sub(lambda m: pinned[f"{m.group(1)}:{tag}"], text), encoding="utf-8")
    env = out / "STANDALONE-SERVICES/standalone-services.env"
    insightface = [ref for ref in pinned if "insightface-rest:" in ref]
    if len(insightface) != 1:
        sys.exit(f"Expected one InsightFace image, got {insightface}")
    with env.open("a", encoding="utf-8") as f:
        f.write(f"\n# Pinned by the release bundle: deploy_trt_multi-gpu.sh pulls exactly this image\n"
                f"INSIGHTFACE_IMAGE='{pinned[insightface[0]]}'\n")
    manifest = {"schema": SCHEMA, "release": tag, "commit": commit, "images": dict(sorted(pinned.items()))}
    (out / "release-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    check(out)
    return manifest


def check(out):
    """Fail if anything other than the allow-list and the manifest is in the bundle, or a source mount survived."""
    found = sorted(p.relative_to(out).as_posix() for p in Path(out).rglob("*") if p.is_file())
    extra = sorted(set(found) - set(FILES) - {"release-manifest.json"})
    if extra:
        sys.exit(f"Not allowed in the bundle: {extra}")
    compose = (Path(out) / "docker-compose-main.yml").read_text(encoding="utf-8")
    if re.search(r"^\s*- \.:", compose, re.M) or "${IMAGE_TAG" in compose or "build:" in compose:
        sys.exit("docker-compose-main.yml mounts the checkout, builds, or uses an unpinned app image")


def demo(keep=None):
    """Builds a bundle from this checkout with made-up digests, then checks it the way a host would read it."""
    tag, tree = "v9.9.9", "0" * 12
    env_text = (ROOT / "STANDALONE-SERVICES/standalone-services.env").read_text(encoding="utf-8")
    refs = app_images((ROOT / "docker-compose-main.yml").read_text(encoding="utf-8"), tag) + [insightface_ref(env_text, tree)]
    digests = {ref: f"sha256:{i:064x}" for i, ref in enumerate(refs, 1)}
    with tempfile.TemporaryDirectory() as out:
        manifest = build(out, tag, "deadbeef", digests)
        compose = (Path(out) / "docker-compose-main.yml").read_text(encoding="utf-8")
        assert len(app_images((ROOT / "docker-compose-main.yml").read_text(encoding="utf-8"), tag)) == 8
        assert compose.count("@sha256:") == 9, compose.count("@sha256:")  # 8 app images + Kafka-WebApp, pinned in git
        assert "INSIGHTFACE_IMAGE='ghcr.io/hamza-aziz-ai/cctv-face-recognition-insightface-rest@sha256:" in \
            (Path(out) / "STANDALONE-SERVICES/standalone-services.env").read_text(encoding="utf-8")
        assert manifest["release"] == tag and len(manifest["images"]) == 9
        assert not [p for p in Path(out).rglob("*.py")], "no Python in the bundle"
        (Path(out) / "src/main.py").write_text("x")
        try:
            check(out)
        except SystemExit as e:
            assert "src/main.py" in str(e)
        else:
            raise AssertionError("a source file in the bundle was not caught")
    try:
        with tempfile.TemporaryDirectory() as out:
            build(out, tag, "deadbeef", {ref: d for ref, d in list(digests.items())[1:]})
    except SystemExit as e:
        assert "No digest" in str(e)
    else:
        raise AssertionError("a missing digest was not caught")
    if keep:
        build(keep, tag, "deadbeef", digests)
    print(f"bundle ok ({len(FILES)} files, {len(refs)} images pinned, source file and missing digest caught)")


if __name__ == "__main__":
    if sys.argv[1:2] == ["demo"] and len(sys.argv) <= 3:
        demo(*sys.argv[2:])
    elif len(sys.argv) == 5:
        build(sys.argv[1], sys.argv[2], sys.argv[3], json.loads(Path(sys.argv[4]).read_text(encoding="utf-8")))
    else:
        sys.exit(__doc__)
