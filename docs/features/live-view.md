# Live view

Each camera's video passed through as it is, beside its latest recognitions, for a client's administrators and viewers (roadmap 8b, D-047). No boxes or names are drawn on the video.

## How it works

- `live-video`, one MediaMTX per client stack, pulls a camera over RTSP (TCP) only while someone watches it and serves it as low-latency HLS. Nothing else is enabled (no RTSP, RTMP, WebRTC, SRT, MoQ or API server), and it publishes no host port.
- The API writes MediaMTX's configuration at start (`src/api/live.py`) from the camera configuration into the Docker volume `live-video-config`, readable by its owner only, as it holds camera passwords. HTTP cameras are left out: MediaMTX pulls RTSP. Restart the API after camera changes.
- The proxy routes `/live/*` to MediaMTX unchanged, behind `forward_auth` to the API's `/live/check`: signed-out visitors go to sign-in, and only `client_admin` and `viewer` get through (`enrolment_operator` gets 403). MediaMTX's paths are named `live/<camera>`, so its own redirects keep the prefix.
- The page is `https://<site host>/api/live`. Each camera starts on **Play**, and the list under it shows that camera's latest recognitions from today and yesterday (name, date, time, score, no images), refreshed every 5 s from `/api/live/events`.

After a release with live view, regenerate each client's proxy route from the release bundle and reload Caddy:

```bash
python deploy/provision.py <client> --proxy
docker exec cctv-proxy caddy reload --config /etc/caddy/Caddyfile
```

## Measured delay (2026-11-03)

Glass to glass, on the owner's laptop with the owner's phone as the camera (H.264 1080p over Wi-Fi). The phone filmed a millisecond clock on the laptop's screen, and each reading compares that clock with the clock as the stream shows it, both from the same laptop clock (±0.02 s).

| Path | Samples | Minimum | Median | Maximum |
|---|---|---|---|---|
| Camera alone: phone, Wi-Fi, RTSP, decoded on the laptop | 10 | 0.79 s | 0.92 s | 2.01 s |
| Live view in the browser: through MediaMTX, HLS and the proxy | 60 | 2.79 s | 3.84 s | 3.92 s |

About 0.9 s is the phone and Wi-Fi, and about 1.9 s is HLS (2 s segments, 0.25 s parts, the player's buffer). The first readings were 2.8 s; after one stall the player stayed 1 s further behind, as MediaMTX's built-in player does not catch up. The owner sees a similar 3 to 4 s delay on the recognition display, which existed before HLS, and attributes it to the RTSP camera stream itself: the owner benchmarked the consumer's batch collection (`BATCH_SIZE` frames per InsightFace request) and found it far smaller. This test measured 0.9 s median and up to 2 s for the phone's RTSP stream read directly; a fixed IP camera on cable was not measured, so how much of the delay a real camera adds is still open.

If the delay matters later: tune HLS with a page of our own using the `hls.js` MediaMTX serves (low-latency mode, catch-up after a stall), or move to WebRTC, which needs a UDP port per host.

## Not covered

- A container of another client's stack on the shared `cctv-edge` network can reach a MediaMTX directly, as it can reach the display: the boundary is the host, as in D-040.
- The phone's uneven frame timing makes MediaMTX warn that low-latency HLS parts could fail on iOS; real cameras with a steady frame rate do not.
- H.265 cameras play only where the browser decodes HEVC.
