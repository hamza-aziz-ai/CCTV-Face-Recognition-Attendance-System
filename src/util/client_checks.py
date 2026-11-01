"""Client separation checks (D-036, D-037): a stack refuses a missing or invalid CLIENT_ID; only the owner may stay on
the legacy shared-service logins; every other stack needs its own logins and never creates databases or topics; two
clients with identical cameras share no database or topic; Milvus binds to the client's own database and login.
Run in the producer-consumer image: python3 src/util/client_checks.py"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

SRC = Path(__file__).resolve().parent.parent
# Both clients name their cameras alike: the names around them must still differ
CAMERAS = {"maingate": {"api-endpoint": "https://ERP_HOST/attendance-endpoint",
                        "cctv-cameras": {"entry": {"cctv-camera-1": {}, "cctv-camera-2": {}}, "exit": None}}}
LOGINS = {"PG_APP_USER": "acme_app", "PG_APP_PASSWORD": "pg-secret", "MILVUS_APP_USER": "acme_app",
          "MILVUS_APP_PASSWORD": "mv-secret", "KAFKA_APP_USER": "acme_app", "KAFKA_APP_PASSWORD": "kf-secret"}
LEGACY = {"LEGACY_SHARED_SERVICES": "1", "POSTGRES_USER": "admin", "POSTGRES_PASSWORD": "admin-secret"}


def names():
    """In a child process: print every name this client's stack uses in the shared servers."""
    sys.path.insert(0, str(SRC))
    import parameters as p
    from util.generic_utilities import count_cameras, map_camera_to_kafka_topic_and_partition
    topics = set(count_cameras()) | {topic for topic, _ in map_camera_to_kafka_topic_and_partition().values()}
    print(json.dumps({"postgres": [p.POSTGRESQL_DATABASE, p.POSTGRESQL_DATABASE_NAME], "milvus": [p.MILVUS_DATABASE],
                      "kafka": sorted(topics)}))


def logins():
    """In a child process: print the logins each shared service would get."""
    sys.path.insert(0, str(SRC))
    import parameters as p
    print(json.dumps({"postgres": p.postgres_login(), "milvus": p.milvus_login(), "kafka": p.kafka_login()}))


def milvus():
    """In a child process: the connection is bound to the client's database and login, or not made at all; only the
    legacy owner creates its database."""
    sys.path.insert(0, str(SRC))
    import milvus_server
    import parameters as p
    user, password = p.milvus_login()
    with mock.patch.object(milvus_server, "connections") as connections, mock.patch.object(milvus_server, "db") as db:
        db.list_database.return_value = ["other"]
        milvus_server.create_connection()
        connections.connect.assert_called_with("default", host=mock.ANY, port=mock.ANY, db_name=p.MILVUS_DATABASE,
                                               user=user, password=password)
        assert db.create_database.called == p.LEGACY_SHARED_SERVICES, "only the legacy owner creates its database"

        connections.reset_mock()
        connections.connect.side_effect = lambda alias, **kw: (_ for _ in ()).throw(RuntimeError("refused")) if alias == "default" else None
        milvus_server.create_connection()  # logged, not raised; the next Milvus call fails for want of a connection
        assert all(call.args[0] != "default" or call.kwargs["db_name"] == p.MILVUS_DATABASE for call in connections.connect.call_args_list)
    print("bound", milvus_server.milvus_token())


def kafka():
    """In a child process: with a topic missing, only the legacy owner creates it; any other stack stops."""
    sys.path.insert(0, str(SRC))
    import parameters as p
    from feedback_server import feedback_message_kafka_publisher as publisher
    with mock.patch.object(publisher, "admin_client") as admin:
        admin.list_topics.return_value.topics = {}
        try:
            publisher.ensure_kafka_topics()
            outcome = "created"
        except RuntimeError as e:
            outcome = "refused" if "deploy/provision.py" in str(e) else str(e)
        assert admin.create_topics.called == (outcome == "created")
    print(outcome, p.KAFKA_TOPIC_PREFIX or "-")


def run(folder, client_id, mode="names", **env):
    environ = {k: v for k, v in os.environ.items() if k not in ("CLIENT_ID", *LOGINS, *LEGACY)}
    environ.update(env)
    if client_id is not None:
        environ["CLIENT_ID"] = client_id
    return subprocess.run([sys.executable, __file__, mode], cwd=folder, env=environ, capture_output=True, text=True)


def ok(result):
    assert result.returncode == 0, result.stderr[-600:]
    return result.stdout.strip().splitlines()[-1]


def test():
    # A folder without master.env, so only the settings given here count
    folder = tempfile.mkdtemp()
    os.makedirs(f"{folder}/src/Camera-Configuration")
    with open(f"{folder}/src/Camera-Configuration/camera_configuration.json", "w") as f:
        json.dump(CAMERAS, f)

    for bad in (None, "", "Acme", "ac", "1acme", "acme_b", "acme.b", "acme-b", "acme b", "a" * 31, "acme\n"):
        result = run(folder, bad)
        assert result.returncode != 0 and "CLIENT_ID in master.env" in result.stderr, (bad, result.stderr)
    result = run(folder, "acme", **LEGACY)
    assert result.returncode != 0 and "owner's site only" in result.stderr, result.stderr

    seen = {"owner-legacy": json.loads(ok(run(folder, "owner", **LEGACY))), "owner": json.loads(ok(run(folder, "owner"))),
            "acme": json.loads(ok(run(folder, "acme"))), "acmeb": json.loads(ok(run(folder, "acmeb")))}
    legacy_names = {"postgres": ["CCTV_Camera_Surveillance", "Face_Recognition_Database"], "milvus": ["default"]}
    assert seen["owner-legacy"] == legacy_names | {"kafka": ["maingate_entry", "maingate_exit"]}, seen["owner-legacy"]
    # After the cutover the owner keeps its data's names, and its topics join everyone's prefix rule
    assert seen["owner"] == legacy_names | {"kafka": ["owner.maingate_entry", "owner.maingate_exit"]}, seen["owner"]
    assert seen["acme"]["kafka"] == ["acme.maingate_entry", "acme.maingate_exit"], seen["acme"]
    for a in ("owner-legacy", "acme", "acmeb"):
        for b in ("owner-legacy", "acme", "acmeb"):
            if a != b:
                shared = {n for names_ in seen[a].values() for n in names_} & {n for names_ in seen[b].values() for n in names_}
                assert not shared, (a, b, shared)
                # Kafka permissions are granted by topic prefix (D-037)
                assert b == "owner-legacy" or not any(t.startswith(f"{b}.") for t in seen[a]["kafka"]), (a, b)

    # Logins: the client's own, from its site .env; a missing one stops the service; the legacy owner keeps the admin one
    got = json.loads(ok(run(folder, "acme", "logins", **LOGINS)))
    assert got == {"postgres": ["acme_app", "pg-secret"], "milvus": ["acme_app", "mv-secret"],
                   "kafka": {"security.protocol": "SASL_PLAINTEXT", "sasl.mechanism": "SCRAM-SHA-512",
                             "sasl.username": "acme_app", "sasl.password": "kf-secret"}}, got
    for key in LOGINS:
        result = run(folder, "acme", "logins", **{k: v for k, v in LOGINS.items() if k != key})
        assert result.returncode != 0 and f"{key} is not set" in result.stderr, (key, result.stderr[-300:])
    result = run(folder, "owner", "logins")  # the owner after its cutover is a client like any other
    assert result.returncode != 0 and "is not set" in result.stderr, result.stderr[-300:]
    assert json.loads(ok(run(folder, "owner", "logins", **LEGACY))) == {"postgres": ["admin", "admin-secret"],
                                                                         "milvus": ["", ""], "kafka": {}}

    assert ok(run(folder, "acme", "milvus", **LOGINS)) == "bound acme_app:mv-secret"
    assert ok(run(folder, "owner", "milvus", **LEGACY)) == "bound root:Milvus"
    assert ok(run(folder, "acme", "kafka", **LOGINS)) == "refused acme."
    assert ok(run(folder, "owner", "kafka", **LEGACY)) == "created -"
    print("clients ok (bad IDs refused, legacy owner only, own logins required, nothing created outside legacy, "
          "two clients share no name, Milvus bound to the client's database and login)")


if __name__ == "__main__":
    {"names": names, "logins": logins, "milvus": milvus, "kafka": kafka}.get(sys.argv[1] if len(sys.argv) > 1 else "", test)()
