# Feature: InsightFace-REST 0.9.5.0 on TensorRT 26.07

Superseded: since D-046 the image is on `tensorrt:26.03-py3` (TensorRT 10.16) for amd64 and arm64, to match DeepStream 9.1. The TensorRT 11 notes below are history.

**Goal:** the latest upstream, on the TensorRT container that matches CUDA toolkit 13.3 (`26.07-py3`: CUDA 13.3.1, TRT 11.1, Python 3.12, driver 610.43 or later).

**Status:** done in a PR (D-031). The running stack switches after the PR merges and `./start_standalone_services.sh` is run.

## What changed

- `src/api_trt` replaced by upstream `if_rest` at `fb854d8`; the entrypoint runs `if_rest.prepare_models` and `if_rest.api.main:app`.
- Dockerfile: TensorRT `26.07-py3` by digest, `libgl1` instead of `libgl1-mesa-glx`, no `python3-opencv`, `cupy-cuda13x`, `pynvjpeg` built with `--no-build-isolation`.
- `requirements.txt`: upstream list, `onnx` and `onnxruntime` unpinned, `onnxconverter-common` added, `PyTurboJPEG==1.8.3`.
- `onnx_to_trt.py`: strongly typed network; FP16 by converting the ONNX weights; `check_fp16()` returns `True`; atomic engine write.
- `getter.py`: engine names end in `_trt<version>.plan`, so the old TensorRT 8.5 engines stay for a rollback.
- `fast_face_align.py`: `np_apply_along_axis` not cached (numba 0.66 failed every request with `cannot pickle '_dynfunc._Closure' object`).
- `face_model.py`: `tobytes()` instead of `tostring()` (NumPy 2 failed every request that returned face crops).

## Test (2026-10-31, on the laptop, beside the running 0.9.0.0)

- Test container with its own models folder, one worker, batch 8/16, FP16: engines built, worker booted, GPU use 3.1 to 3.6 GB.
- LFW, 30 people with 11+ photos, 5 enrolled and 6 tested each: old 173 correct, 0 wrong, 7 below; new the same. Same-photo embeddings: cosine min 0.9951, mean 0.9993 over 180 photos.
- The app's `IFRClient` (from the `producer-consumer:v2.0.3` image): 4 images, msgpack and JSON, all `ok`, same face fields as the old service.

## Not verified

- CCTV footage, and the two-worker setup that shares one models folder.
- Speed against the old version.
- The CPU image.

## Log

- 2026-10-30: trial image built; TRT 11 port done; engine step passed; worker boot failed on PyTurboJPEG. Trial image deleted.
- 2026-10-31: PyTurboJPEG pinned to 1.8.3; numba and NumPy 2 failures found and fixed; LFW and client tests passed.
