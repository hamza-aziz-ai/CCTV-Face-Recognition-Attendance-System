# Cutover: per-client logins on the shared services (D-037, step 3c)

This runbook switches one host from the admin logins and open services to per-client logins. It is done once per host, by the owner, in one sitting, with the deploy watcher paused. Plan for about an hour.

The owner's displays go blank for a few minutes. Messages sent during the switch are missed, because displays hold no history. No stored data is moved or deleted.

## Before you start

1. These are merged and released, and the release is `:stable`:
   - client IDs (#61);
   - per-client stacks (#62, #63);
   - provisioning (#64);
   - app logins (#65);
   - this change.
2. A Kafka-WebApp release that has SASL logins, every partition and `PROJECT_SERVICES` is pinned in `docker-compose-main.yml`.
3. The host runs from the bundle layout (roadmap item 5): `sites\owner\` holds the owner's `.env`, `master.env` (with `CLIENT_ID=owner` and `LEGACY_SHARED_SERVICES=1`) and `src\Camera-Configuration\camera_configuration.json`, and `provision.py` sits beside `watch.py`.
4. The owner's stack runs and works on that release.

## Steps

Run these in the deploy folder. Commands that use the admin login run inside the service's own container, so its password is never typed.

1. **Pause the watcher**, so no release starts mid-switch:
   `schtasks /Change /TN "CCTV deploy watcher" /DISABLE`
2. **Back up PostgreSQL:**
   `docker exec cctv-postgresql sh -c 'pg_dumpall -U "$POSTGRES_USER"' > C:\deploy\backup\postgres-before-d037.sql`
   Check that the file is not empty. Milvus vectors can be rebuilt from the dataset (D-030), and Kafka holds nothing durable.
3. **Stop the owner's stack:**
   `docker compose -p cctv stop`
4. **Restart Kafka with logins.** This also removes Schema Registry, Connect, ksqlDB, REST Proxy and Flink; their volumes stay. From the release's `STANDALONE-SERVICES\Confluent-Kafka`:
   `docker compose --env-file ..\standalone-services.env up -d --remove-orphans`
   Then check that the broker is healthy: `docker ps --filter name=broker`.
5. **Restart Milvus with authorization.** From `STANDALONE-SERVICES\Milvus-Vector-Database`:
   `docker compose --env-file ..\standalone-services.env up -d`
6. **Set up the host's admin logins.** This replaces Milvus root's default password and creates the read-only Kafbat login. Both passwords go to `admin.env` in the deploy folder; keep that file off every client's site.
   `python provision.py --init-milvus-root`
   `python provision.py --init-kafbat`
7. **Provision the owner:**
   `python provision.py owner`
   This creates `owner_app` in PostgreSQL and hands it the owner's databases, tables, partitions and sequences, one by one. It also creates the owner's Milvus user on the `default` database (the existing alias stays), Kafka users and `owner.*` topics from the camera configuration, and the `owner-enrolment` bucket. The new passwords are added to `sites\owner\.env`. Run the same command for every other client on this host.
8. **Switch the owner's site to its own logins.** Edit these yourself:
   - `sites\owner\master.env`: delete the `LEGACY_SHARED_SERVICES=1` line. Set `KAFKA_TOPIC=owner.<location>_<point>` for the in-stack display.
   - `sites\owner\.env`: delete `POSTGRES_USER` and `POSTGRES_PASSWORD`. The shared PostgreSQL keeps its own copy, in the standalone services' `.env`.
9. **Start the owner's stack:**
   `python watch.py --enroll owner`
   It deploys the current release with the new settings and runs the usual smoke and stability checks.
10. **Verify:**
    - `curl -s -o NUL -w "%{http_code}" localhost:9090/docs` prints 200.
    - Nothing is restarting: `docker ps --filter label=com.docker.compose.project=cctv`.
    - A recognition reaches the display. Walk past a camera, or play a clip.
    - The services' environments hold only their own keys. List names only, never values: `docker exec cctv-mfr-api-service-1 env | findstr /B "PG_APP POSTGRES"` should list `PG_APP_USER` and `PG_APP_PASSWORD`, and no `POSTGRES_` keys.
    - The default Milvus password no longer works: `curl -s -X POST localhost:19530/v2/vectordb/users/list -H "Authorization: Bearer root:Milvus" -d "{}"` returns a non-zero `code`.
11. **Switch the Raspberry Pi displays.** Set:
    - `KAFKA_USERNAME=owner_display`;
    - `KAFKA_PASSWORD` to `KAFKA_DISPLAY_PASSWORD` from `sites\owner\.env`;
    - `KAFKA_TOPIC=owner.<location>_<point>`;
    - `IP_ADDRESS` to this host.

    Restart each display.
12. **Resume the watcher:**
    `schtasks /Change /TN "CCTV deploy watcher" /ENABLE`

A week later, delete the old unprefixed topics (`maingate_entry` and the like) with `docker exec broker kafka-topics --bootstrap-server localhost:29092 --delete --topic <name>`.

## Rolling back

Releases from before #65 cannot run against these services, so roll back the settings, not the release:

1. Pause the watcher, if it is running.
2. Put `LEGACY_SHARED_SERVICES=1` back in `sites\owner\master.env`, and `POSTGRES_USER` / `POSTGRES_PASSWORD` back in `sites\owner\.env`.
3. Start the previous Kafka and Milvus compose files: plaintext Kafka with its add-ons, and Milvus without `user.yaml`. Use the previous release's `STANDALONE-SERVICES` folder.
4. `python watch.py --enroll owner`.

The admin PostgreSQL login is a superuser, so it reaches the owner's data whoever owns it. The old unprefixed topics are still there, and the legacy mode uses them.

If PostgreSQL data was damaged, restore the dump from step 2, into a stopped stack, with `psql -U "$POSTGRES_USER" -f` inside the container.

## What this has been rehearsed against

`deploy/test_isolation.py` runs this sequence on throwaway copies of the four services. It seeds owner data made the old way: admin-owned databases, a partitioned table with a serial column, and a published Milvus version behind the alias. It then checks that:
- `owner_app` writes the old tables and adds partitions;
- no table is left owned by the admin login;
- the alias is untouched;
- other clients and the owner are refused on each other's data;
- the Kafbat login reads every topic and writes none.

The live Kafka data was also rehearsed under the new listener settings, on 2026-10-31. A read-only copy of `confluent-kafka_kafka-data` (2.9 GB) went into a throwaway broker on its own network, using `STANDALONE-SERVICES/auth/kafka.env` with the same `CLUSTER_ID`. It was healthy after 15 seconds, with every existing topic listed and no `ERROR` in its log. A new SCRAM login listed only the topic it was allowed, and the plaintext listener was unreachable from another container. The copy was then deleted. If the broker still does not come up in step 4, roll back as above and keep the logs.
