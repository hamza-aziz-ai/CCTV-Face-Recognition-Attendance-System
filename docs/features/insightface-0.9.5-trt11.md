# Feature: InsightFace-REST 0.9.5.0 on TensorRT 26.07

**Goal:** the latest upstream, on the TensorRT container that matches CUDA toolkit 13.3 (`26.07-py3`: CUDA 13.3.1, TRT 11.1, Python 3.12, driver 610.43 or later).

**Status:** on hold. The running stack stays on 0.9.0.0 with TRT 8.5.

**Scope:** upstream restructured to `if_rest/` and gunicorn, so the vendored copy is replaced, not patched. `deploy_trt_multi-gpu.sh`, the entrypoint module name and the engine folder change too. nginx gets pinned to `1.30.6` in the same PR.

## Steps found so far

Dockerfile (from upstream `dockerfiles/Dockerfile_trt`):

- `FROM nvcr.io/nvidia/tensorrt:26.07-py3@sha256:b82db1abc23750ab0069abc99bbe4ea29138dbdc23ea39861199e2346638b48a`
- `libgl1-mesa-glx` becomes `libgl1`; drop `python3-opencv`.
- `cupy-cuda12x` becomes `cupy-cuda13x`.
- `pynvjpeg` needs `pip install cython setuptools`, then `pip install --no-build-isolation pynvjpeg`.

`requirements.txt`: unpin `onnx` and `onnxruntime`, add `onnxconverter-common`.

`if_rest/core/converters/onnx_to_trt.py`, because TRT 11 removed `EXPLICIT_BATCH`, `BuilderFlag.FP16` and `platform_has_fast_fp16`:

- Create the network with `STRONGLY_TYPED`.
- For FP16: `float16.convert_float_to_float16(onnx.load_from_string(input_onnx), keep_io_types=True)` before parsing.
- `check_fp16()` returns `True`.

## Open

- **Next blocker:** gunicorn fails to boot: `PyTurboJPEG 2.0 requires libjpeg-turbo 3.0 or later`. Options: pin PyTurboJPEG 1.x, or install libjpeg-turbo 3.
- Check whether the app's client still works with the 0.9.5 API.
- Compare embeddings with the old engine: FP16 by ONNX conversion may change results.

## Log

- 2026-10-30: trial image built; TRT 11 port done; engine step passed; worker boot failed on PyTurboJPEG. Trial image deleted.
