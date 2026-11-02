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

## TensorRT in a container

TensorRT 10.16.2.10 installs on plain Ubuntu 24.04 and runs on the GPU in a container. Engines built on the host loaded and ran inside it, with no material speed loss:

| Engine | Host | Container |
|---|---|---|
| `rec_b1` | 369 batches/s, 2.6 ms | 340 batches/s, 3.0 ms |
| `rec_b32` | 19.7 batches/s, 51 ms | 19.8 batches/s, 50 ms |
| `det_b1` | 188 batches/s, 5.8 ms | 190 batches/s, 5.5 ms |
| `det_b8` | 25.9 batches/s, 41 ms | 26.0 batches/s, 41 ms |

The image is 6.18 GB, and it took about 5.5 minutes to build, 4 of them exporting layers. Build it with no time limit. It needs `jetson-ota-public.asc` beside the Dockerfile, copied from `/etc/apt/trusted.gpg.d/` on the Jetson.

```dockerfile
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
COPY jetson-ota-public.asc /etc/apt/trusted.gpg.d/jetson-ota-public.asc
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates python3 python3-numpy \
    && printf 'deb https://repo.download.nvidia.com/jetson/common r39.2 main\ndeb https://repo.download.nvidia.com/jetson/som r39.2 main\n' > /etc/apt/sources.list.d/nvidia-l4t.list \
    && mkdir -p /opt/nvidia/l4t-packages && touch /opt/nvidia/l4t-packages/.nv-l4t-disable-boot-fw-update-in-preinstall \
    && apt-get update \
    && apt-get install -y --no-install-recommends libnvinfer-bin python3-libnvinfer \
    && rm -rf /var/lib/apt/lists/*
```

The apt repo is `som`, not `t234`, on JetPack 7.2.1. An image only fits the JetPack release in its repo line, here r39.2.

## What this means

- The x86 image cannot run here: it is amd64, on TensorRT 11, and its base image has no `l4t` build for r39.2.1.
- The GPU and CUDA libraries reach a plain `ubuntu:24.04` container with `--runtime nvidia --gpus all`, but TensorRT does not, so the image must install it. The Dockerfile below does this from NVIDIA's Jetson apt repo.
- SCRFD must be reshaped with the project's `reshape_onnx.py` before building; a fixed model per batch size worked.
- The Orin Nano has no hardware encoder (NVENC), so nothing here should re-encode video.

## Not yet tested

Real faces, real accuracy on TensorRT 10, InsightFace-REST itself, building engines inside a container, CPU load, several camera streams at once, and Milvus on this board.
