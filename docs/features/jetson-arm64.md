# Jetson Orin Nano: arm64 spike

Findings from 2026-11-02 on the owner's Orin Nano Super developer kit (8 GB, JetPack 7.2.1, CUDA 13.2, TensorRT 10.16.2.10, MAXN_SUPER). This is roadmap item 12.

## Result so far

Native TensorRT builds and runs both of our real models on the Jetson's GPU, in FP16. These are `trtexec` figures on synthetic input, 300 iterations each. They exclude video decode, image preparation, post-processing, Milvus and Kafka, so a real pipeline will be slower.

| Model | Batch | Batches/s | Items/s | Median latency | Engine build | Peak RAM |
|---|---|---|---|---|---|---|
| `w600k_r50` recognition | 1 | 369 | 369 faces | 2.6 ms | 81 s | 3.2 GB |
| `w600k_r50` recognition | 16 | 38.4 | 614 faces | 26 ms | 261 s | 3.4 GB |
| `w600k_r50` recognition | 32 | 19.7 | 629 faces | 51 ms | 365 s | 3.5 GB |
| `scrfd_10g_gnkps` detection, 640x640 | 1 | 188 | 188 frames | 5.8 ms | 86 s | 2.7 GB |
| `scrfd_10g_gnkps` detection, 640x640 | 4 | 50.9 | 203 frames | 21 ms | 151 s | 2.7 GB |
| `scrfd_10g_gnkps` detection, 640x640 | 8 | 25.9 | 207 frames | 41 ms | 234 s | 2.7 GB |
| `scrfd_10g_gnkps` detection, 640x640 | 16 | 12.9 | 207 frames | 83 ms | 397 s | 2.9 GB |

Peak RAM is the whole board's memory in use during the run, and the GPU shares that 8 GB. The GPU peaked at 70 °C in the recognition runs.

Batching gains little on detection, about 10%, and adds latency, so small batches suit this board. Each engine takes minutes to build, so engines should be built once and kept with the host's data, as the x86 deployment does.

## What this means

- The x86 image cannot run here: it is amd64, on TensorRT 11, and its base image has no `l4t` build for r39.2.1.
- The GPU and CUDA libraries reach a plain `ubuntu:24.04` container with `--runtime nvidia --gpus all`, but TensorRT does not, so it has to be added to the image.
- SCRFD must be reshaped with the project's `reshape_onnx.py` before building; a fixed model per batch size worked.
- The Orin Nano has no hardware encoder (NVENC), so nothing here should re-encode video.

## Not yet tested

Real faces, real accuracy on TensorRT 10, InsightFace-REST itself, TensorRT inside a container, CPU load, several camera streams at once, and Milvus on this board.
