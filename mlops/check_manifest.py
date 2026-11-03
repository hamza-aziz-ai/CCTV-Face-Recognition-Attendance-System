"""Fail if mlops/model-manifest.json drifts from the code and config it describes.

Run from the repo root: python mlops/check_manifest.py [--release]
--release also fails while any manifest value is still null (unverified).
Reads source files as text, never imports them, so it needs no project dependencies.
"""
import ast
import json
import re
import sys
from pathlib import Path


def literals(path):
    """Top-level NAME = <literal> assignments of a Python file."""
    out = {}
    for node in ast.parse(Path(path).read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


def env(path):
    pairs = (line.split("=", 1) for line in Path(path).read_text(encoding="utf-8").splitlines() if "=" in line and not line.startswith("#"))
    return {k.strip(): v.strip().strip("'\"") for k, v in pairs}


def number(pattern, text):
    return float(re.search(pattern, text).group(1))


def nulls(node, path=""):
    if node is None:
        yield path
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from nulls(v, f"{path}.{k}" if path else k)


def check(m, root="."):
    root = Path(root)
    p = literals(root / "src/parameters.py")
    e = env(root / "STANDALONE-SERVICES/standalone-services.env")
    models = json.loads((root / "STANDALONE-SERVICES/InsightFace-REST/models/models.json").read_text(encoding="utf-8"))
    milvus = (root / "src/milvus_server.py").read_text(encoding="utf-8")
    params_text = (root / "src/parameters.py").read_text(encoding="utf-8")
    dockerfile = (root / "STANDALONE-SERVICES/InsightFace-REST/src/Dockerfile_trt").read_text(encoding="utf-8")
    det, rec, vs, pipe, svc = m["detector"], m["recognizer"], m["vector_store"], m["pipeline"], m["inference_service"]

    expected = {
        "inference_service.image": (svc["image"], f"{e['IMAGE']}:{e['TAG']}"),  # CI appends -<git tree of src>
        "inference_service.base_image": (svc["base_image"], re.search(r"^FROM (\S+)", dockerfile, re.M).group(1)),
        "inference_service.fp16": (svc["fp16"], e["FP16"] == "True"),
        "inference_service.max_size": (svc["max_size"], [int(x) for x in e["MAX_SIZE"].split(",")]),
        "detector.name": (det["name"], e["DETECTION_MODEL"]),
        "detector.max_batch_size": (det["max_batch_size"], int(e["DETECTION_BATCH_SIZE"])),
        "detector.threshold": (det["threshold"], float(e["DETECTION_THRESHOLD"])),
        "detector.input_shape": (det["input_shape"], models[det["name"]]["shape"]),
        "detector.onnx_md5_expected": (det["onnx_md5_expected"], models[det["name"]]["md5"]),
        "recognizer.name": (rec["name"], e["RECOGNITION_MODEL"]),
        "recognizer.max_batch_size": (rec["max_batch_size"], int(e["RECOGNITION_BATCH_SIZE"])),
        "recognizer.input_shape": (rec["input_shape"], models[rec["name"]]["shape"]),
        "recognizer.onnx_md5_expected": (rec["onnx_md5_expected"], models[rec["name"]]["md5"]),
        "recognizer.embedding_dim": (rec["embedding_dim"], int(number(r"FLOAT_VECTOR, dim=(\d+)", milvus))),
        "vector_store.metric": (vs["metric"], p["METRIC_TYPE"]),
        "vector_store.index_type": (vs["index_type"], p["INDEX_TYPE"]),
        "vector_store.index_params.nlist": (vs["index_params"]["nlist"], int(number(r'"nlist": (\d+)', milvus))),
        "vector_store.search_params.nprobe": (vs["search_params"]["nprobe"], int(number(r'"nprobe": (\d+)', milvus))),
        "vector_store.top_k": (vs["top_k"], int(number(r"limit=(\d+)", milvus))),
        # FACE_MATCHING_TOLERANCE depends on MATCH_METRIC in master.env (D-049), so ast cannot evaluate it; take the COSINE default
        "vector_store.match_distance_tolerance": (vs["match_distance_tolerance"], number(r'os\.getenv\("COSINE_THRESHOLD", "([\d.]+)"\)', params_text)),
        "vector_store.match_metric_toggle.L2.default": (vs["match_metric_toggle"]["L2"]["default"], number(r'os\.getenv\("L2_THRESHOLD", "([\d.]+)"\)', params_text)),
        "vector_store.filter_fields": (sorted(vs["filter_fields"]), sorted(re.findall(r'name="(departments)"', milvus))),
        "pipeline.frame_size": (pipe["frame_size"], [p["FRAME_WIDTH"], p["FRAME_HEIGHT"]]),
        "pipeline.batch_size": (pipe["batch_size"], p["BATCH_SIZE"]),
        "pipeline.pupil_distance_threshold_px": (pipe["pupil_distance_threshold_px"], p["PUPIL_DISTANCE_THRESHOLD"]),
        "pipeline.liveness_enabled": (pipe["liveness_enabled"], p["ENABLE_FACE_LIVENESS_DETECTION"]),
    }
    for name, d in m["datasets"].items():
        out = re.search(r"md5: (\S+)\s+size: (\d+)\s+nfiles: (\d+)", (root / f"{name}.dvc").read_text(encoding="utf-8"))
        expected[f"datasets.{name}"] = ([d["dvc_md5"], d["bytes"], d["files"]], [out.group(1), int(out.group(2)), int(out.group(3))])

    return [f"{k}: manifest={got!r} source={want!r}" for k, (got, want) in expected.items() if got != want]


def demo():
    """Self-check of the checker itself, on a tampered copy: drift and nulls are both detected."""
    m = json.loads(Path("mlops/model-manifest.json").read_text(encoding="utf-8"))
    m["recognizer"]["embedding_dim"] = -1
    assert any(e.startswith("recognizer.embedding_dim") for e in check(m))
    assert list(nulls({"a": {"b": None, "c": 1}})) == ["a.b"]


if __name__ == "__main__":
    demo()
    manifest = json.loads(Path("mlops/model-manifest.json").read_text(encoding="utf-8"))
    errors = check(manifest)
    missing = [k for k in nulls(manifest)]
    for err in errors:
        print(f"DRIFT {err}")
    for k in missing:
        print(f"UNVERIFIED {k}: {manifest['unverified'].get(k, 'no instructions')}")
    if errors or ("--release" in sys.argv and missing):
        sys.exit(1)
    print(f"manifest ok ({len(missing)} unverified)")
