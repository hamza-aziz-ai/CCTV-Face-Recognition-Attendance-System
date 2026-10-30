# Failure map

Marked **seen** where it actually happened on this host, otherwise **from the code**, not tested. There are no alerts or dashboards: you find out from `docker ps`, the service logs under `logs/`, `deploy/watch.log`, or a Windows message from the watcher.

| Dependency | If it is down, slow or wrong | How you notice | Status |
|---|---|---|---|
| Camera | Thread loses frames; other cameras continue | Producer log | From the code |
| InsightFace-REST | No embeddings, so no recognition; frames keep queuing | Container unhealthy, consumer log | From the code |
| Frame queue | Unbounded `multiprocessing.Queue`: memory grows if recognition is slower than the cameras; contents are lost on restart | Host memory | From the code |
| Milvus down | Searches fail while running | Consumer log | From the code |
| Milvus MinIO | Crash loop when an older build opens data from a newer one | `Restarting` in `docker ps` | Seen |
| Kafka | Displays stop updating; attendance still recorded | Display shows an error message | From the code |
| Kafka restart | The producer deletes and recreates topics, so pending feedback is lost | Missing display messages | From the code |
| PostgreSQL | Results are not stored; retry behaviour not confirmed | DB controller log | From the code |
| DB controller | The duplicate check queries a column the table does not define (README, Known issues) | Log errors | From the code |
| ERP | Records wait for the next minute's attempt | API log | From the code |
| Camera unreachable | Thread logs the error, sleeps 30 s and retries; `producer-consumer` stays Up | Producer log | Seen |
| Nightly updater | Swallows insert failures and still marks rows processed, so vectors are lost silently | Nothing | From the code |
| Docker Desktop | Everything stops until someone signs in to Windows (D-018) | Displays go down | From the design |
| Host IP change | Kafka advertises the old IP; run `set_configuration.sh` and restart Kafka | Clients cannot connect | From the design |
| ghcr.io login | Deploy fails and rolls back | Watcher message | From the design |
| GPU memory | 3.3 of 6 GB used idle; batches 8/16 are unmeasured guesses | OOM in InsightFace log | Not measured |

## First limits to hit

1. GPU memory on this laptop, once real frames flow.
2. Frame queue growth, if cameras outrun recognition.
3. Laptop disk: 24 GB of datasets, the frames stored in Postgres, plus images.
4. One host: there is no redundancy for anything.

A real run has not happened yet, so these limits are estimates.
