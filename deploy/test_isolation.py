"""Client isolation on the shared services (D-036 step 3), on throwaway copies of them: PostgreSQL, Kafka, Milvus and
MinIO under a random isotest-* compose project, with the same authentication settings as production
(STANDALONE-SERVICES/auth). Provisions clients acme and beta with deploy/provision.py, then checks:
  - each client can use its own databases, topics, collections and bucket (positive control first);
  - each is refused, with an explicit authorisation error, on the other's, and on admin actions;
  - Kafka's plaintext listeners are unreachable from other containers and anonymous clients are refused;
  - reruns change nothing, an interrupted run finishes on rerun, a lost password stops provisioning;
  - Milvus root's default password is replaced; everything still holds after the services restart.
Needs Docker; pulls about 3.5 GB of images the first time. Never touches the live services or their data.
Run from the repo root: python3 -I deploy/test_isolation.py"""
import hashlib
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import provision  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
AUTH = REPO / "STANDALONE-SERVICES" / "auth"
PROJECT = f"isotest-{secrets.token_hex(4)}"
MILVUS_IMAGE = "milvusdb/milvus:v3.0.5@sha256:b9b79b4a284b41cd12d60abc418310f84621fa4c977d409b38f501519a7ccf8a"
KAFKA_IMAGE = "confluentinc/cp-kafka:8.4.0"
# ClusterAuthorization: a Java producer is idempotent by default, which Kafka allows only with Write on some topic
DENIED = ("TopicAuthorization", "GroupAuthorization", "ClusterAuthorization", "Not authorized", "Authorization failed")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def fixture(tmp, milvus_port):
    (tmp / "embedEtcd.yaml").write_text("listen-client-urls: http://0.0.0.0:2379\nadvertise-client-urls: http://0.0.0.0:2379\n")
    return f"""name: {PROJECT}
services:
  postgres:
    image: postgres:18.6-trixie
    environment: {{POSTGRES_USER: admin, POSTGRES_PASSWORD: {secrets.token_hex(12)}}}
    healthcheck: {{test: ["CMD-SHELL", "pg_isready -U admin"], interval: 3s, retries: 40}}
  kafka:
    image: {KAFKA_IMAGE}
    hostname: kafka
    env_file: ["{(AUTH / 'kafka.env').as_posix()}"]
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:29092,CLIENTS://kafka:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "false"
      CLUSTER_ID: SXNvbGF0aW9uVGVzdENsdXN0
    healthcheck: {{test: ["CMD", "kafka-broker-api-versions", "--bootstrap-server", "localhost:29092"], interval: 5s, retries: 40}}
  milvus:
    image: {MILVUS_IMAGE}
    command: ["milvus", "run", "standalone"]
    security_opt: ["seccomp:unconfined"]
    environment: {{DEPLOY_MODE: STANDALONE, ETCD_USE_EMBED: "true", ETCD_DATA_DIR: /var/lib/milvus/etcd,
                  ETCD_CONFIG_PATH: /milvus/configs/embedEtcd.yaml, COMMON_STORAGETYPE: local}}
    volumes:
      - "{(tmp / 'embedEtcd.yaml').as_posix()}:/milvus/configs/embedEtcd.yaml:ro"
      - "{(AUTH / 'milvus-user.yaml').as_posix()}:/milvus/configs/user.yaml:ro"
    ports: ["127.0.0.1:{milvus_port}:19530"]
    healthcheck: {{test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"], interval: 5s, retries: 60}}
  store:
    image: pgsty/minio:RELEASE.2026-08-04T00-00-00Z@sha256:b6bfe7239bfc83fb90d31612d9704d86039dd714f7904b3f1ad68f211e602372
    command: server /data
    environment: {{MINIO_ROOT_USER: admin, MINIO_ROOT_PASSWORD: {secrets.token_hex(12)}}}
    healthcheck: {{test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"], interval: 3s, retries: 40}}
"""


def sh(*cmd, stdin=None, check=True):
    p = subprocess.run(cmd, input=stdin.encode() if stdin else None, capture_output=True, timeout=600)
    p.stdout, p.stderr = p.stdout.decode(errors="replace"), p.stderr.decode(errors="replace")  # bytes in: no CR added on Windows
    if check and p.returncode != 0:
        raise AssertionError(f"{' '.join(cmd[:6])}: {(p.stderr or p.stdout).strip()[-400:]}")
    return p


class Fixture:
    def __init__(self, tmp):
        self.tmp, self.port = tmp, free_port()
        self.compose_file = tmp / "compose.yml"
        self.compose_file.write_text(fixture(tmp, self.port))
        self.sites, self.admin_env = tmp / "sites", tmp / "admin.env"
        self.milvus = f"http://127.0.0.1:{self.port}"

    def compose(self, *args):
        assert PROJECT.startswith("isotest-")  # cleanup only ever targets this run's project
        return sh("docker", "compose", "-p", PROJECT, "-f", str(self.compose_file), *args)

    def container(self, service):
        return self.compose("ps", "-q", service).stdout.strip()

    def up(self):
        self.compose("up", "-d", "--wait", "--wait-timeout", "600")
        self.pg, self.kafka, self.store = (self.container(s) for s in ("postgres", "kafka", "store"))
        for _ in range(60):  # Milvus answers health before its proxy takes requests
            try:
                provision.milvus_call(self.milvus, "root:Milvus", "users/list", {})
                return
            except RuntimeError as e:
                if "code 1800" in str(e) or "code 2" in str(e):  # authentication refused: it is up
                    return
                time.sleep(5)

    def provision(self, client, **override):
        args = [client, "--sites", str(self.sites), "--admin-env", str(self.admin_env), "--postgres", self.pg,
                "--kafka", self.kafka, "--store", self.store, "--milvus", self.milvus]
        for key, value in override.items():
            args[args.index(f"--{key}") + 1] = value
        return provision.main(args)

    def env(self, client):
        return provision.read_env(self.sites / client / ".env")


# ---- each system, as a client ------------------------------------------------------------------------------------

def psql(f, env, db, sql):
    return sh("docker", "exec", "-i", "-e", f"PGPASSWORD={env['PG_APP_PASSWORD']}", f.pg, "psql", "-X", "-h", "127.0.0.1",
              "-U", env["PG_APP_USER"], "-d", db, "-v", "ON_ERROR_STOP=1", stdin=sql, check=False)


def kafka_tool(f, env, user_key, *cmd, stdin=None):
    props = (f"security.protocol=SASL_PLAINTEXT\nsasl.mechanism=SCRAM-SHA-512\nrequest.timeout.ms=8000\n"
             f"default.api.timeout.ms=15000\nsasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule "
             f"required username=\"{env[user_key]}\" password=\"{env[user_key.replace('USER', 'PASSWORD')]}\";\n")
    path = f"/tmp/{env[user_key]}.props"
    sh("docker", "exec", "-i", f.kafka, "sh", "-c", f"cat > {path}", stdin=props)
    flag = {"kafka-console-producer": "--producer.config", "kafka-console-consumer": "--consumer.config"}.get(cmd[0], "--command-config")
    return sh("docker", "exec", "-i", f.kafka, cmd[0], "--bootstrap-server", "kafka:9092", flag, path, *cmd[1:],
              stdin=stdin, check=False)


def produce(f, env, user_key, topic):
    p = kafka_tool(f, env, user_key, "kafka-console-producer", "--topic", topic, stdin="hello\n")
    return p.stdout + p.stderr


def consume(f, env, topic, group):
    p = kafka_tool(f, env, "KAFKA_DISPLAY_USER", "kafka-console-consumer", "--topic", topic, "--group", group,
                   "--from-beginning", "--max-messages", "1", "--timeout-ms", "20000")
    return p.stdout + p.stderr


def milvus(f, env, path, body):
    try:
        return provision.milvus_call(f.milvus, f"{env['MILVUS_APP_USER']}:{env['MILVUS_APP_PASSWORD']}", path, body)
    except RuntimeError as e:
        return e


def mc(f, env, script):
    head = f"mc alias set c http://localhost:9000 {env['STORE_APP_ACCESS_KEY']} {env['STORE_APP_SECRET_KEY']} >/dev/null\n"
    p = sh("docker", "exec", "-i", f.store, "sh", "-s", stdin=head + script, check=False)
    return p.returncode, p.stdout + p.stderr


def denied(text, *markers):
    return any(m in str(text) for m in markers or DENIED)


# ---- checks ------------------------------------------------------------------------------------------------------

def check_own(f, env, client):
    db = f"{client}_cctv_camera_surveillance"
    # The runtime DDL path: the DB controller creates partitioned tables and partitions as it goes
    out = psql(f, env, db, "CREATE TABLE IF NOT EXISTS r (y int, who text) PARTITION BY RANGE (y);\n"
                           "CREATE TABLE IF NOT EXISTS r_2026 PARTITION OF r FOR VALUES FROM (2026) TO (2027);\n"
                           f"INSERT INTO r VALUES (2026, '{client}');\nSELECT count(*) FROM r;\n")
    assert out.returncode == 0, (client, "own postgres", out.stderr[-300:])
    assert psql(f, env, f"{client}_face_recognition_database", "SELECT 1;\n").returncode == 0, (client, "own 2nd db")
    db_m, topic = f"{client}_default", f"{client}.maingate_entry"
    for path, body in (("collections/create", {"dbName": db_m, "collectionName": "FACES_v1", "dimension": 8}),
                       ("entities/insert", {"dbName": db_m, "collectionName": "FACES_v1", "data": [{"id": 1, "vector": [0.1] * 8}]}),
                       ("aliases/create", {"dbName": db_m, "collectionName": "FACES_v1", "aliasName": "FACES"})):
        result = milvus(f, env, path, body)
        assert not isinstance(result, Exception) or "exist" in str(result), (client, path, result)
    # D-030 publish: a new numbered version, then the alias moves to it
    milvus(f, env, "collections/create", {"dbName": db_m, "collectionName": "FACES_v2", "dimension": 8})
    assert not isinstance(milvus(f, env, "aliases/alter", {"dbName": db_m, "collectionName": "FACES_v2", "aliasName": "FACES"}), Exception)
    assert not isinstance(milvus(f, env, "entities/query", {"dbName": db_m, "collectionName": "FACES_v1", "filter": "id >= 0",
                                                            "outputFields": ["id"]}), Exception), (client, "own query")
    out = produce(f, env, "KAFKA_APP_USER", topic)
    assert not denied(out) and "ERROR" not in out, (client, "own produce", out[-300:])
    out = consume(f, env, topic, f"{topic}.display")
    assert "hello" in out, (client, "own consume", out[-300:])
    code, out = mc(f, env, f"echo {client} | mc pipe c/{client}-enrolment/probe.txt >/dev/null && mc cat c/{client}-enrolment/probe.txt\n")
    assert code == 0 and client in out, (client, "own bucket", out[-300:])


def check_refused(f, env, client, other):
    for db in (f"{other}_cctv_camera_surveillance", f"{other}_face_recognition_database", "postgres"):
        out = psql(f, env, db, "SELECT 1;\n")
        assert out.returncode != 0 and "permission denied for database" in out.stderr, (client, db, out.stderr[-200:])
    for sql in ("CREATE DATABASE evil;\n", "CREATE ROLE evil;\n"):
        out = psql(f, env, f"{client}_cctv_camera_surveillance", sql)
        assert "permission denied" in out.stderr, (client, sql, out.stderr[-200:])
    for db in (f"{other}_default", "default"):
        for path, body in (("collections/create", {"dbName": db, "collectionName": "EVIL", "dimension": 8}),
                           ("entities/query", {"dbName": db, "collectionName": "FACES_v1", "filter": "id >= 0", "outputFields": ["id"]}),
                           ("entities/insert", {"dbName": db, "collectionName": "FACES_v1", "data": [{"id": 9, "vector": [0.1] * 8}]}),
                           ("aliases/alter", {"dbName": db, "collectionName": "FACES_v1", "aliasName": "FACES"}),
                           ("collections/drop", {"dbName": db, "collectionName": "FACES_v1"})):
            result = milvus(f, env, path, body)
            assert denied(result, "permission deny", "PermissionDenied"), (client, db, path, result)
    for path, body in (("databases/create", {"dbName": "evil"}), ("users/create", {"userName": "evil", "password": "Evil-123456"}),
                       ("users/grant_role", {"userName": env["MILVUS_APP_USER"], "roleName": "admin"})):
        assert denied(milvus(f, env, path, body), "permission deny", "PermissionDenied"), (client, path)
    topic = f"{other}.maingate_entry"
    assert denied(produce(f, env, "KAFKA_APP_USER", topic)), (client, "produce to other")
    assert denied(produce(f, env, "KAFKA_DISPLAY_USER", f"{client}.maingate_entry")), (client, "display writes")
    out = kafka_tool(f, env, "KAFKA_APP_USER", "kafka-topics", "--create", "--topic", f"{client}.new", "--partitions", "1")
    assert denied(out.stdout + out.stderr), (client, "app creates topic")
    assert denied(consume(f, env, topic, f"{client}.maingate_entry.display"), "TopicAuthorization", "Not authorized to access topics"), (client, "read other topic")
    assert denied(consume(f, env, f"{client}.maingate_entry", f"{other}.maingate_entry.display"), "GroupAuthorization", "Not authorized to access group"), (client, "other group")
    out = kafka_tool(f, env, "KAFKA_DISPLAY_USER", "kafka-topics", "--list")
    assert f"{other}." not in out.stdout, (client, "lists other topics")
    for action in (f"mc ls c/{other}-enrolment", f"mc cat c/{other}-enrolment/probe.txt", f"echo x | mc pipe c/{other}-enrolment/evil.txt",
                   f"mc rm c/{other}-enrolment/probe.txt", f"mc ls --versions c/{other}-enrolment", "mc mb c/evil-bucket"):
        code, out = mc(f, env, action + "\n")
        assert code != 0 and denied(out, "Access Denied", "Insufficient permissions"), (client, action, out[-200:])
    code, out = mc(f, env, "mc ls c\n")
    assert f"{other}-enrolment" not in out, (client, "lists other bucket")


def check_kafka_boundary(f):
    # Plaintext listeners answer only on the broker's loopback, so no other container gets the superuser
    net = f"{PROJECT}_default"
    p = sh("docker", "run", "--rm", "--network", net, "--entrypoint", "kafka-broker-api-versions", KAFKA_IMAGE,
           "--bootstrap-server", "kafka:29092", check=False)
    assert p.returncode != 0, "plaintext listener reachable from another container"
    p = sh("docker", "run", "--rm", "--network", net, "--entrypoint", "sh", KAFKA_IMAGE, "-c",
           "printf 'request.timeout.ms=5000\\ndefault.api.timeout.ms=8000\\n' > /tmp/p && "
           "kafka-topics --bootstrap-server kafka:9092 --command-config /tmp/p --list", check=False)
    assert p.returncode != 0 and "maingate" not in p.stdout, "anonymous client served on 9092"


def seed_topics(f):
    for client in ("acme", "beta", "gamma"):
        sh("docker", "exec", f.kafka, "kafka-topics", "--bootstrap-server", "localhost:29092", "--create", "--if-not-exists",
           "--topic", f"{client}.maingate_entry", "--partitions", "2")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test():
    tmp = Path(tempfile.mkdtemp(prefix="isotest-"))
    f = Fixture(tmp)
    try:
        f.up()
        # Root's default password goes; a rerun is a no-op; the default is refused from then on
        assert provision.main(["--init-milvus-root", "--admin-env", str(f.admin_env), "--milvus", f.milvus]) == 0
        assert provision.main(["--init-milvus-root", "--admin-env", str(f.admin_env), "--milvus", f.milvus]) == 0
        assert isinstance(milvus(f, {"MILVUS_APP_USER": "root", "MILVUS_APP_PASSWORD": "Milvus"}, "users/list", {}), Exception)
        seed_topics(f)
        # The owner's vectors live in Milvus's default database: seed some, so refusals there are real ones
        root = {"MILVUS_APP_USER": "root", "MILVUS_APP_PASSWORD": provision.read_env(f.admin_env)["MILVUS_ROOT_PASSWORD"]}
        for path, body in (("collections/create", {"dbName": "default", "collectionName": "FACES_v1", "dimension": 8}),
                           ("entities/insert", {"dbName": "default", "collectionName": "FACES_v1", "data": [{"id": 1, "vector": [0.1] * 8}]}),
                           ("aliases/create", {"dbName": "default", "collectionName": "FACES_v1", "aliasName": "FACES"})):
            assert not isinstance(milvus(f, root, path, body), Exception), path
        assert f.provision("owner") == 1 and f.provision("Acme") == 1  # owner waits for 3c; bad IDs refused
        for client in ("acme", "beta"):
            assert f.provision(client) == 0, client
        before = {c: digest(f.sites / c / ".env") for c in ("acme", "beta")}
        assert f.provision("acme") == 0 and digest(f.sites / "acme/.env") == before["acme"], "rerun changed credentials"
        acme, beta = f.env("acme"), f.env("beta")
        assert not set(acme) - set(provision.settings("acme")), "admin or other keys in a client's .env"
        check_own(f, acme, "acme")
        check_own(f, beta, "beta")
        check_refused(f, acme, "acme", "beta")
        check_refused(f, beta, "beta", "acme")
        check_kafka_boundary(f)

        # Interrupted after each service in turn: every rerun reuses the saved passwords and finishes
        saved = None
        for broken in ("milvus", "kafka", "store"):
            with mock.patch.object(provision, broken, side_effect=RuntimeError(f"{broken} interrupted")):
                assert f.provision("gamma") == 1
            saved = saved or digest(f.sites / "gamma/.env")
            assert digest(f.sites / "gamma/.env") == saved, "passwords changed on rerun"
        assert f.provision("gamma") == 0 and digest(f.sites / "gamma/.env") == saved
        gamma = f.env("gamma")
        check_own(f, gamma, "gamma")
        # A lost password stops provisioning, on every rerun, instead of resetting the account under the running stack
        env_file = f.sites / "gamma/.env"
        env_file.write_text("".join(line + "\n" for line in env_file.read_text().splitlines() if not line.startswith("PG_APP_PASSWORD=")))
        trimmed = digest(env_file)
        assert f.provision("gamma") == 1 and f.provision("gamma") == 1 and digest(env_file) == trimmed
        assert psql(f, gamma, "gamma_cctv_camera_surveillance", "SELECT 1;\n").returncode == 0, "old password was reset"

        f.compose("restart")
        f.up()
        check_own(f, acme, "acme")
        check_refused(f, acme, "acme", "beta")
        assert isinstance(milvus(f, {"MILVUS_APP_USER": "root", "MILVUS_APP_PASSWORD": "Milvus"}, "users/list", {}), Exception)
        print("isolation ok (2 clients: own access on 4 services, cross-client and admin actions refused, Kafka plaintext "
              "unreachable, reruns and interruptions safe, lost password stops, Milvus root replaced, holds after restart)")
    finally:
        f.compose("down", "-v", "--remove-orphans")


if __name__ == "__main__":
    test()
