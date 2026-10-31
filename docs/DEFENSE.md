# DEFENSE: CCTV Face Recognition Attendance System

## What It Does

This system uses CCTV cameras to recognize people and automatically record their attendance. Whenever someone is identified, their details appear on a display, and their attendance is sent to the institution's ERP system.

The idea is to make attendance tracking easier without requiring people to manually check in.

## How It Works

The process starts with CCTV cameras capturing video frames. These frames are added to a queue and processed on the GPU, where faces are detected and converted into embeddings. The embeddings are then searched against the stored face data to identify the person.

Once a match is found, the attendance is recorded in PostgreSQL, sent to the ERP, and shown on the display.

There's also a nightly job that collects recent face images. This helps the system recognize people even when their appearance changes over time.

The complete workflow is documented in [FLOW.md](FLOW.md).

## Key Decisions and Why I Made Them

- **Vector search instead of direct face comparison:** Comparing every detected face against thousands of stored images would be too slow. Vector search makes matching much faster, even with tens of thousands of face images.
- **A separate staging collection:** People's appearances change over time, which can affect recognition accuracy. I kept a separate collection for newer face embeddings so the system can adapt without modifying the original enrolled data.
- **Kafka only for feedback:** I avoided sending video frames through Kafka because frame processing needs to be fast. Kafka is used for feedback messages, while displays receive a continuous stream of recognition results.
- **Pull-based deployment:** The deployment machine pulls new releases instead of accepting incoming deployment requests. This reduces the need to expose the machine to external access.

I've covered the alternatives and trade-offs in [ALTERNATIVES.md](ALTERNATIVES.md).

## Data Structures and Why

For face recognition, I use 512-dimensional embeddings stored in Milvus. Cosine similarity is used to find the closest matching faces.

Attendance records are stored separately in PostgreSQL. The tables are partitioned by year and location, making it easier to manage records and keep attendance reports efficient as the data grows.

More details are available in [DATA.md](DATA.md).

## How Someone Could Misuse the System

One of the biggest concerns with the current setup is security. Most internal services can be accessed over the network without authentication.

Someone with network access could potentially create fake attendance records, access stored facial data, or insert misleading data that affects recognition accuracy.

Another weakness is that liveness detection is currently disabled. This means someone could potentially fool the system using a printed photograph instead of appearing in person.

These risks are discussed in [THREAT.md](THREAT.md).

## Where It Can Fail and How I Detect It

The biggest limitation right now is the hardware. Since the system runs on a laptop, GPU memory becomes a bottleneck when processing too many frames.

The system also depends on an active Windows login session. If nobody is signed in, the services stop running.

Another issue is the nightly update job. It can fail to save some face embeddings without reporting an obvious error, which may affect recognition later.

There isn't a proper alerting system in place yet, so identifying these issues still requires manual checks.

I've documented the failure scenarios in [FAILURE.md](FAILURE.md).

## What I Would Improve With More Time

My first priority would be security. I'd restrict network access, add authentication to internal services, and enable liveness detection to reduce the chances of someone spoofing attendance.

I'd also add proper monitoring and alerts so failures don't go unnoticed, along with regular backups to protect the data.

Finally, I'd move the system from the laptop to a dedicated server. That would remove the dependency on a Windows login session and provide a more reliable environment for running it continuously.