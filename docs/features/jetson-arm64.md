# Jetson Orin Nano: arm64 spike

Findings from 2026-11-02 on the owner's Orin Nano Super developer kit (8 GB, JetPack 7.2.1, CUDA 13.2, TensorRT 10.16.2.10, MAXN_SUPER). This is roadmap item 12.

## Engine benchmarks

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

## NVIDIA's TensorRT image

`nvcr.io/nvidia/l4t-tensorrt:r10.3.0` is the newest tag. It is older than the board's own stack, but it works on JetPack 7.2.1: Ubuntu 22.04, Python 3.10, TensorRT 10.3.0 and CUDA 12.6 inside the image, with the GPU reached through the nvidia runtime. Figures are `trtexec` at batch 1, on engines built in each image with the same fixed-size SCRFD model:

| Image | Size on disk | Digest | Recognition | Detection |
|---|---|---|---|---|
| `r10.3.0-devel` | 12.4 GB | `sha256:602c0972ae06...` | 371 faces/s, 2.9 ms, built in 82 s | 186 frames/s, 5.8 ms, built in 104 s |
| `r10.3.0-runtime`, engines from `devel` | 4.48 GB | `sha256:2c5dd352de34...` | 353 faces/s, 2.9 ms | 186 frames/s, 5.8 ms |
| `r10.3.0-runtime`, engine built inside it | 4.48 GB | `sha256:2c5dd352de34...` | Not built | 184 frames/s, built in 102 s |

These match the host's TensorRT 10.16 speeds. The `runtime` image has `trtexec` and the Python `Builder` and ONNX parser, but no `numpy`, so the InsightFace-REST image must install its Python requirements on top. Engines built on TensorRT 10.16 will not load here, so the 10.3 engines are built separately.

## InsightFace-REST on the Jetson

InsightFace-REST 0.9.5 runs on the Jetson from `STANDALONE-SERVICES/InsightFace-REST/src/Dockerfile_trt_jetson`, on `l4t-tensorrt:r10.3.0-runtime`, with the laptop's model, batch and threshold settings (`DET_BATCH_SIZE=8`, `REC_BATCH_SIZE=16`, `NUM_WORKERS=1`). The image is 6.18 GB. With no engines yet, first start took about 6.5 minutes and peaked at 4.7 GB of board memory; later starts take seconds.

Each image in `src/test_images` went to the Jetson and to the laptop (TensorRT 11, amd64). Both found the same faces in all 5 images, 119 faces in total:

| Measure | Result |
|---|---|
| Embedding cosine, Jetson against laptop | Minimum 0.9955, mean 0.9989 |
| Detection confidence | Within 0.002 on the faces read |
| Face position | Within 0.5 px on the faces read |

Load test on the Jetson itself, posting one image in a loop for 20 s per level:

| Clients | One face per request | Four faces per request |
|---|---|---|
| 1 | 42.5 requests/s, 24 ms | 29.6 requests/s, 34 ms |
| 2 | 48.4 requests/s, 41 ms | 34.5 requests/s, 58 ms |
| 4 | 48.1 requests/s, 84 ms | 34.6 requests/s, 118 ms |
| 8 | 48.8 requests/s, 164 ms | 35.4 requests/s, 223 ms |
| 16 | 49.8 requests/s, 324 ms | 35.3 requests/s, 457 ms |

Latency is the median. Throughput flattens at about 49 requests/s, or 141 faces/s with four faces per request. The one server process stays near 115% CPU while the GPU peaks at 78% and 65 °C, so the limit is that Python process, not the GPU. The board's CPU was not saturated. The container used about 1 GB of memory, 1.8 GB after a fresh engine build.

Differences from the amd64 image:

- `onnx_to_trt.py` sets FP16 with the builder flag on TensorRT 10, because the ONNX conversion path needs TensorRT 11's strongly typed networks.
- The 1 GB builder workspace limit stays off on TensorRT 10. With it, `w600k_r50` at batch 16 failed with `Could not find any implementation for node PWN(PRelu_1)`.
- `icc-rt` has no arm64 build, `onnx-simplifier` is never imported, and `tritonclient` needs `gevent`, which would not build here. All three are left out.
- CuPy compiles at run time, so it needs the CUDA headers. `nvidia-cuda-runtime-cu12` supplies them; the `[ctk]` extra also works but adds 4 GB.
- JPEGs decode with TurboJPEG, as nvJPEG is not used here.

### Two workers

With `NUM_WORKERS=2` the same load test, on warm workers:

| Clients | One face per request | Four faces per request |
|---|---|---|
| 1 | 41.5 requests/s, 24 ms | Not measured warm |
| 2 | 57.0 requests/s, 35 ms | 41.5 requests/s, 51 ms |
| 4 | 73.5 requests/s, 57 ms | 55.2 requests/s, 76 ms |
| 8 | 76.2 requests/s, 107 ms | 53.6 requests/s, 151 ms |
| 16 | 77.4 requests/s, 210 ms | 54.0 requests/s, 301 ms |

That is about 55% more than one worker: 216 faces/s with four faces per request. The container uses 2.37 GB, and the board 3.3 GB in all. Each worker's first request after a start took about 26 s, so a client with a 30 s timeout can fail once; send a warm-up request before taking traffic.

Three workers reached 90.4 requests/s with one face and 246.8 faces/s with four, only 14 to 17% more than two, for 3.7 GB, 1.35 GB more. Two workers is the setting for this board, leaving memory for the producer-consumer and the controllers.

## Live camera through the Jetson

On 2026-11-02 the producer-consumer, database controller and feedback controller ran on the Jetson as arm64 images, built there from the unchanged `main.Dockerfile`, `database-server.Dockerfile` and `feedback-server.Dockerfile` (2.06, 1.58 and 1.53 GB). Recognition used the Jetson's InsightFace-REST, published on 6385, while Milvus, Kafka and PostgreSQL stayed on the laptop, reached over the LAN. `master.env` on the Jetson kept `IP_ADDRESS` as the laptop and set `INSIGHTFACE_HOST=http://<jetson>`. The dynamic face dataset collector was left out, so no face crops were kept on the Jetson.

One camera, the owner's phone over RTSP, with the owner in front of it and one person enrolled:

| Measure | Result |
|---|---|
| Records in 80 s | 39, all the enrolled person, no other name |
| Score | Minimum 0.482, mean 0.709, maximum 0.784 |
| Laptop on the same camera, earlier | Minimum 0.603, mean 0.715, maximum 0.774 |
| Producer-consumer | About 266% CPU, 1 GB |

Scores under 0.5 count only when the staging collection also matches, which accepts down to 0.45 by design. The test read and cleared its rows every 2 s, as the duplicate window otherwise keeps one record per person. The phone's stream dropped and reconnected 5 times. The room's dark start halted recognition until a light was on, as on the laptop. This is one person and one camera, not an accuracy figure.

The owner's display showed the name within a second, so the Jetson's feedback controller reached the laptop's Kafka and the display read it.

### More cameras

The same phone stream entered as 1, 2 and 4 cameras, 60 s each, with InsightFace-REST on two workers and the owner in front of it:

| Cameras | Records per minute | Score min, mean | GPU, average | Producer-consumer CPU | InsightFace-REST CPU |
|---|---|---|---|---|---|
| 1 | 28 | 0.471, 0.609 | 15% | 219% | 24% |
| 2 | 60, 30 per camera | 0.478, 0.646 | 34% | 291% | 26% |
| 4 | 108, 27 per camera | 0.469, 0.687 | 56% | 437% | 68% |

Records grew with the cameras, nothing was purged from the frame buffer, and no stream dropped. The board's 6 CPU cores carry the producer-consumer at about 4.4 of them with 4 cameras, so CPU, not the GPU, is the likely limit beyond that; frames here are 640x360 after resizing. Every display message in these runs went to camera 1's partition, because the feedback controller reads its camera map once at start and only the producer-consumer was restarted between runs. A rerun with all three restarted caught too few recognitions to check. The feedback controller must be restarted after cameras change.

## One image on TensorRT 26.03

Since D-046, InsightFace-REST is one image for both architectures, built from `Dockerfile_trt` on `nvcr.io/nvidia/tensorrt:26.03-py3` (TensorRT 10.16.0.72, CUDA 13.2), whose arm64 build runs on the Orin Nano under JetPack 7.2.1. `Dockerfile_trt_jetson` and its `l4t-tensorrt:r10.3.0` base are gone. Compared on 2026-11-03 against each machine's previous image, with the same 5 test images and settings:

| | Laptop, against TensorRT 11.1 | Jetson, against `l4t-tensorrt` TensorRT 10.3 |
|---|---|---|
| Faces found | 119 and 119, the same faces | 119 and 119, the same faces |
| Embedding cosine | Minimum 0.9988, mean 0.9998 | Minimum 0.9983, mean 0.9998 |
| Detection confidence | Within 0.0016 | Within 0.0009 |
| Face position | Within 1 px | Within 1 px |
| One image per request | 18.3 ms before, 17.4 ms after | 30.7 ms before, 29.9 ms after |
| Image build | 26 s, base already pulled | 353 s |
| First start, building engines | About 170 s | 345 s, board peak 3.7 GB |
| Image size | 19.1 GB | 21.5 GB, against 6.18 GB before |

`trtexec` on the base alone ran `w600k_r50` at 291 batches/s at batch 1 on the Jetson. Engine file names carry the TensorRT version, so the new engines sit beside the old ones and either image can start.

## What this means

- An amd64-only image cannot run here; every image we publish now has an arm64 build (D-044, D-046).
- InsightFace-REST runs on NVIDIA's multi-arch `tensorrt:26.03-py3`, the same image as on x86 (D-046). It carries its own CUDA and TensorRT and builds engines at startup.
- A plain `ubuntu:24.04` container also gets the GPU and CUDA libraries with `--runtime nvidia --gpus all`, but not TensorRT. The Dockerfile above is the fallback for that route.
- SCRFD must be reshaped with the project's `reshape_onnx.py` before building; a fixed model per batch size worked.
- The Orin Nano has no hardware encoder (NVENC), so nothing here should re-encode video.

## Not yet tested

Accuracy on a labelled set, an unenrolled person, real separate cameras, more than 4 cameras, the display with more than one camera, the dynamic face dataset collector (an edge node's crops go to its client's collector, D-043), Milvus or Kafka on this board, and the images GitHub builds for arm64 (D-044) running here. The load test repeats one image; real frames vary.
