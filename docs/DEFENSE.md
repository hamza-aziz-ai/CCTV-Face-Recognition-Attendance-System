# DEFENSE: CCTV Face Recognition Attendance System

**AI draft. The guide says this must end up in your own words: rewrite it, then delete this line.**

## What it does

Recognises people on CCTV cameras and marks their attendance automatically. It shows each recognised person on a display and sends the records to the institution's ERP.

## How it works

Cameras -> frame queue -> GPU detection and embeddings -> vector search -> Postgres, ERP and displays. A nightly job adds fresh face crops, so matching keeps up with how people look now. Full path in [FLOW.md](FLOW.md).

## Key decisions and why X over Y

- Vector search instead of comparing faces one by one, because it stays fast at tens of thousands of images.
- A second, staging collection, to recognise people whose appearance has changed, without touching enrolled data.
- Kafka only for feedback, not frames, because frames need speed and displays need a stream.
- The deploy host pulls releases, so nothing outside can push to it.

More in [ALTERNATIVES.md](ALTERNATIVES.md).

## Data structures and why

512-number embeddings in Milvus with cosine search; attendance in Postgres, partitioned by year and location so reports stay fast. See [DATA.md](DATA.md).

## How a malicious actor could abuse it

Today, anyone on the network can reach most services with no login: forge attendance, read face data, or poison matching. A printed photo can also pass, because liveness detection is off. See [THREAT.md](THREAT.md).

## Where it fails and how we notice

GPU memory first, on this laptop. Everything stops if nobody is signed in to Windows. The nightly job can lose vectors silently. There are no alerts yet. See [FAILURE.md](FAILURE.md).

## What I would change with more time

Lock down the network, add login to internal services, turn on liveness, add alerts and backups, and move off the laptop.
