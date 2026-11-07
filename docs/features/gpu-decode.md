# GPU video decoding and frame transport

The producer can decode camera streams on the GPU's video decoder (NVDEC) instead of the CPU, and can send frames to InsightFace-REST uncompressed instead of as JPEG. Both are `master.env` settings with the original behaviour kept as the fallback (D-045).

## Settings

| Key in `master.env` | Values | Default | What it does |
|---|---|---|---|
| `VIDEO_DECODE` | `auto`, `gpu`, `cpu` | `auto` | `gpu`: FFmpeg decodes each stream with the codec's NVDEC decoder (`h264_cuvid`, `hevc_cuvid`, ...), which also scales frames to 640x360, and pipes them to the producer. `cpu`: OpenCV decodes on the CPU, the original path. `auto`: `gpu`, falling back to `cpu` for any connection the GPU cannot open (no GPU, no decoder library, a codec NVDEC lacks, no VRAM left). |
| `FRAME_TRANSPORT` | `jpeg`, `bmp` | `jpeg` | `jpeg`: base64 JPEG in JSON, the original. `bmp`: uncompressed BMP in a msgpack body, which InsightFace-REST already accepts, so it needs no change. |

Restart the producer-consumer after changing either. Any other `VIDEO_DECODE` value stops the services at start with a message naming it. Use `cpu` on a Jetson: its hardware decoder is not NVDEC, so `auto` would try `h264_cuvid`, log `Cannot load libnvcuvid.so.1` and fall back to the CPU on every connection. A camera with a region of interest gets full-size frames from the GPU, as the region is cropped from them, so only the decoding moves to the GPU for it.

RTSP is read over TCP, as OpenCV reads it. FFmpeg's default, UDP, failed from Docker Desktop on the owner's phone camera (`Error during demuxing: Operation not permitted`), so v2.10.0 fell back to the CPU for every real camera; with TCP the same stream decoded on NVDEC at 17 fps with 1% Python CPU, against 35% on the CPU path (2026-11-03).

The producer-consumer service reserves the GPU with `capabilities: [gpu, compute, video]`. `video` gives the container the NVDEC library, `libnvcuvid`; Docker Desktop on WSL2 also mounts it once asked, so no host-specific mount is needed.

## Measured on the laptop (2026-11-03)

RTX 4050 Laptop (one NVDEC), i7-13700H. The 1080p30 H.264 sample from DeepStream, published as N RTSP cameras by MediaMTX, read the way the producer reads (read, scale to 640x360, darkness check), 30 s per run. CPU is the container's, 100% = one core.

| Cameras | v2.9.3 (OpenCV, full-frame darkness check) | New CPU path | GPU (NVDEC) |
|---|---|---|---|
| 4 | 475%, 30 fps | 141%, 30 fps | 36%, 30 fps |
| 8 | 859%, 26.9 fps (behind) | 319%, 29.8 fps | 56%, 28.6 fps |
| 16 | not run | 1,339%, 25.2 fps (behind) | 135%, 30 fps |

The new CPU path is also faster than v2.9.3 because of two changes that apply to both decoders: the darkness check runs on the 640x360 frame instead of blurring the full frame (23 of the 39 ms per 1080p frame), and the producer process runs OpenCV on one thread per camera, as its thread pool on top of the camera threads cost about 40% more CPU.

GPU costs:

- VRAM: about 131 MB per camera, mostly the CUDA context of each camera's FFmpeg process. Scaling with `scale_cuda` instead of the decoder took 203 MB. 16 cameras used 2.1 GB on top of the 2.2 GB already in use.
- NVDEC: 64% busy at 16 cameras of 1080p30.
- So this laptop's limit is about 24 cameras of 1080p30, where NVDEC and the 6 GB of VRAM run out together. A camera beyond that falls back to the CPU in `auto`.

Frame transport, 8 frames of 640x360 per request to the laptop's InsightFace-REST:

| Transport | Round trip per batch | Producer CPU per batch |
|---|---|---|
| `jpeg` | 71 ms | 11.1 ms |
| `bmp` | 119 ms | 4.8 ms |

`bmp` saves about 0.8 ms of producer CPU per frame but moves 15 times the bytes (5.5 MB per batch), and here that made each batch slower. It suits InsightFace-REST on the same machine only when the producer's CPU is the limit, and never a remote InsightFace-REST. Skipping InsightFace-REST's EXIF scan for non-JPEG bytes made no measurable difference, so InsightFace-REST is unchanged.

## Not covered

- The Jetson: its FFmpeg has no NVDEC decoders, so `auto` falls back to the CPU there. GPU decoding on the Jetson needs GStreamer's `nvv4l2decoder`, a separate change. The Orin Nano's one NVDEC handles about 11 streams of 1080p30 by NVIDIA's figures, below the 15 to 20 stream target, so measure it there first.
- Accuracy is unchanged in principle, as frames are scaled to the same 640x360, but NVDEC's scaler is not OpenCV's `INTER_AREA`. Not measured on a labelled set.
