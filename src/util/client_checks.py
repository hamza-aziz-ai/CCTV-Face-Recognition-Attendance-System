"""Client separation checks (D-036): a stack refuses a missing or invalid CLIENT_ID, the owner keeps the names it had,
two clients with identical cameras share no database or topic, and Milvus binds to the client's database.
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


def names():
    """In a child process with CLIENT_ID set: print every name this client's stack uses in the shared servers."""
    sys.path.insert(0, str(SRC))
    import parameters as p
    from util.generic_utilities import count_cameras, map_camera_to_kafka_topic_and_partition
    topics = set(count_cameras()) | {topic for topic, _ in map_camera_to_kafka_topic_and_partition().values()}
    print(json.dumps({"postgres": [p.POSTGRESQL_DATABASE, p.POSTGRESQL_DATABASE_NAME], "milvus": [p.MILVUS_DATABASE],
                      "kafka": sorted(topics)}))


def milvus():
    """In a child process with CLIENT_ID=acme: the connection is bound to acme's database, or not made at all."""
    sys.path.insert(0, str(SRC))
    import milvus_server
    with mock.patch.object(milvus_server, "connections") as connections, mock.patch.object(milvus_server, "db") as db:
        db.list_database.return_value = ["default"]
        milvus_server.create_connection()
        db.create_database.assert_called_once_with("acme_default", using="setup")
        connections.connect.assert_called_with("default", host=mock.ANY, port=mock.ANY, db_name="acme_default")

        db.reset_mock()
        db.list_database.return_value = ["default", "acme_default"]
        milvus_server.create_connection()
        db.create_database.assert_not_called()

        connections.reset_mock()
        db.list_database.return_value = ["default"]
        db.create_database.side_effect = RuntimeError("denied")
        milvus_server.create_connection()
        assert all(call.args[0] != "default" for call in connections.connect.call_args_list), "no fallback connection"
    print("bound")


def run(folder, client_id, mode="names"):
    env = {k: v for k, v in os.environ.items() if k != "CLIENT_ID"}
    if client_id is not None:
        env["CLIENT_ID"] = client_id
    return subprocess.run([sys.executable, __file__, mode], cwd=folder, env=env, capture_output=True, text=True)


def test():
    # A folder without master.env, so only the CLIENT_ID given here counts
    folder = tempfile.mkdtemp()
    os.makedirs(f"{folder}/src/Camera-Configuration")
    with open(f"{folder}/src/Camera-Configuration/camera_configuration.json", "w") as f:
        json.dump(CAMERAS, f)

    for bad in (None, "", "Acme", "ac", "1acme", "acme_b", "acme.b", "acme-b", "acme b", "a" * 31, "acme\n"):
        result = run(folder, bad)
        assert result.returncode != 0 and "CLIENT_ID in master.env" in result.stderr, (bad, result.stderr)

    seen = {}
    for client_id in ("owner", "acme", "acmeb"):
        result = run(folder, client_id)
        assert result.returncode == 0, result.stderr
        seen[client_id] = json.loads(result.stdout)
    assert seen["owner"] == {"postgres": ["CCTV_Camera_Surveillance", "Face_Recognition_Database"], "milvus": ["default"],
                             "kafka": ["maingate_entry", "maingate_exit"]}, seen["owner"]
    assert seen["acme"]["kafka"] == ["acme.maingate_entry", "acme.maingate_exit"], seen["acme"]
    for a in seen:
        for b in seen:
            if a != b:
                shared = {n for names_ in seen[a].values() for n in names_} & {n for names_ in seen[b].values() for n in names_}
                assert not shared, (a, b, shared)
                # Kafka permissions are granted by topic prefix (D-036 step 3)
                assert b == "owner" or not any(t.startswith(f"{b}.") for t in seen[a]["kafka"]), (a, b)

    result = run(folder, "acme", "milvus")
    assert result.returncode == 0 and result.stdout.strip() == "bound", result.stderr
    print("clients ok (bad IDs refused, owner names kept, two clients share no name, Milvus bound to the client's database)")


if __name__ == "__main__":
    {"names": names, "milvus": milvus}.get(sys.argv[1] if len(sys.argv) > 1 else "", test)()
