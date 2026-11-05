"""Versioned face vectors (D-030).

enrol_person.py saves each person's vectors next to their photos, in FACIAL-RECOGNITION-DATASET/<person_id>/vectors.parquet,
so one DVC version of the dataset holds both. Milvus serves MILVUS_COLLECTION_NAME as an alias of a numbered collection
(<name>_v1, <name>_v2, ...) built from those files, and pointing the alias at an older collection is the rollback. The
app keeps using the alias name and follows a switch without a restart.

Usage: python3 src/util/face_vectors.py publish    build the next version from the dataset and switch to it
       python3 src/util/face_vectors.py use <n>    switch to version n, e.g. back to the previous one
       python3 src/util/face_vectors.py list       the versions, and the one in use
       python3 src/util/face_vectors.py migrate    once: vectors from the photos, the live collection becomes version 0
       python3 src/util/face_vectors.py demo       self-check, needs no services
"""
import os
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from pymilvus import MilvusClient

current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
sys.path.append(parent)

from milvus_server import create_collection, create_connection, insert_data, milvus_token
from parameters import FACIAL_RECOGNITION_DATASET_PATH, MILVUS_COLLECTION_NAME, MILVUS_DATABASE, MILVUS_STAGING_COLLECTION_NAME, MILVUS_HOST, MILVUS_PORT,     POSTGRESQL_DATABASE, POSTGRESQL_HOST, POSTGRESQL_PORT, postgres_login

VECTORS_FILE = "vectors.parquet"
KEEP = 3  # versions kept in Milvus; the dataset in DVC rebuilds any older one
BATCH = 5000  # rows per insert, well under the 64 MB gRPC message limit at 2 KB a vector


def save(folder, person_id, vectors):
    vectors = [np.asarray(vector, dtype=np.float32) for vector in vectors]
    pd.DataFrame({"name_id": [person_id] * len(vectors), "embeddings": vectors}).to_parquet(Path(folder) / VECTORS_FILE, index=False)


def load(dataset):
    frames = [pd.read_parquet(path) for path in sorted(Path(dataset).glob(f"*/{VECTORS_FILE}"))]
    if not frames:
        return [], []
    rows = pd.concat(frames, ignore_index=True)
    return rows["name_id"].tolist(), [np.asarray(vector, dtype=np.float32).tolist() for vector in rows["embeddings"]]


def departments_of(rows):
    """{person_id: departments} from roster rows (person_id, department, extra_departments): lowercase, sorted, unique."""
    return {person: sorted({name.strip().lower() for name in [department or "", *(extra or [])] if name and name.strip()})
            for person, department, extra in rows}


def roster_departments():
    """Each person's departments from this client's roster (D-049). No roster yet means no departments; an unreachable
    database stops the publish, since a version without departments would hide everyone from department cameras."""
    import psycopg2
    user, password = postgres_login()
    with psycopg2.connect(dbname=POSTGRESQL_DATABASE, user=user, password=password, host=POSTGRESQL_HOST,
                          port=POSTGRESQL_PORT, connect_timeout=5) as conn, conn.cursor() as db:
        db.execute("SELECT to_regclass('persons') IS NOT NULL")
        if not db.fetchone()[0]:
            return {}
        db.execute("ALTER TABLE persons ADD COLUMN IF NOT EXISTS extra_departments TEXT[] NOT NULL DEFAULT '{}'")
        db.execute("SELECT person_id, department, extra_departments FROM persons")
        return departments_of(db.fetchall())


def versions(collection_names, alias):
    pattern = re.compile(re.escape(alias) + r"_v(\d+)")
    return sorted(int(match[1]) for name in collection_names if (match := pattern.fullmatch(name)))


def connect():
    create_connection(host=MILVUS_HOST, port=MILVUS_PORT)
    return MilvusClient(uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}", token=milvus_token(), db_name=MILVUS_DATABASE)


def in_use(client, alias):
    # Listed first: describe_alias on a missing alias works, but pymilvus logs it as an error with a traceback
    if alias not in client.list_aliases()["aliases"]:
        return None
    return client.describe_alias(alias)["collection_name"]


def refuse_unless_migrated(client, alias):
    if in_use(client, alias) is None and client.has_collection(alias):
        sys.exit(f"{alias} is still a plain collection: run `python3 src/util/face_vectors.py migrate` first")


def build(client, dataset, alias, allow_empty=False):
    names, vectors = load(dataset)
    if not names and not allow_empty:
        sys.exit(f"No {VECTORS_FILE} under {dataset}: an empty version would stop all recognition")
    roster = roster_departments()
    departments = [roster.get(name, []) for name in names]
    number = max(versions(client.list_collections(), alias), default=0) + 1
    collection = create_collection(f"{alias}_v{number}", with_departments=True)
    for start in range(0, len(names), BATCH):
        insert_data(collection, [names[start:start + BATCH], vectors[start:start + BATCH], departments[start:start + BATCH]])
    return number


def use(client, alias, number):
    target, old = f"{alias}_v{number}", in_use(client, alias)
    client.load_collection(target)
    if old is None:
        client.create_alias(target, alias)
    else:
        client.alter_alias(target, alias)
    if old not in (None, target):
        client.release_collection(old)  # only the version in use takes GPU memory
    print(f"{alias} now serves {target}")


def publish(dataset=FACIAL_RECOGNITION_DATASET_PATH, alias=MILVUS_COLLECTION_NAME):
    client = connect()
    refuse_unless_migrated(client, alias)
    use(client, alias, build(client, dataset, alias))
    for number in versions(client.list_collections(), alias)[:-KEEP]:
        if f"{alias}_v{number}" != in_use(client, alias):
            client.drop_collection(f"{alias}_v{number}")
            print(f"Dropped {alias}_v{number}")


def forget(person_id, dataset=FACIAL_RECOGNITION_DATASET_PATH, alias=MILVUS_COLLECTION_NAME, staging=MILVUS_STAGING_COLLECTION_NAME):
    """Deletion (8e), after the person's folder is gone from the dataset: a version without them when the one in use
    still holds them (empty if they were the last), then every other version is dropped, since any may hold them and
    only the version in use is loaded to check. A rollback after this is rebuilt from the dataset. Staging loses their
    nightly vectors. Safe to run again."""
    client = connect()
    refuse_unless_migrated(client, alias)
    serving = in_use(client, alias)
    person = f'name_id == "{person_id}"'  # IDs hold only letters, digits, ".", "_" and "-"
    if serving and client.query(serving, filter=person, output_fields=["name_id"], limit=1):
        use(client, alias, build(client, dataset, alias, allow_empty=True))
        serving = in_use(client, alias)
    for number in versions(client.list_collections(), alias):
        if f"{alias}_v{number}" != serving:
            client.drop_collection(f"{alias}_v{number}")
            print(f"Dropped {alias}_v{number}")
    if client.has_collection(staging):
        client.load_collection(staging)  # a delete by filter needs the collection loaded
        client.delete(staging, filter=person)


def migrate(dataset=FACIAL_RECOGNITION_DATASET_PATH, alias=MILVUS_COLLECTION_NAME):
    from enrol_person import vectors_for  # here, not at the top: enrol_person imports this module

    client = connect()
    if in_use(client, alias):
        sys.exit(f"{alias} is already an alias of {in_use(client, alias)}")
    # Rows share a person's ID as their primary key, so a query returns one row per person: enough to list them,
    # but the vectors themselves are taken again from the photos
    client.load_collection(alias)
    enrolled = {row["name_id"] for row in client.query(alias, filter='name_id != ""', output_fields=["name_id"], limit=16384)}
    missing = sorted(person for person in enrolled if not (Path(dataset) / person).is_dir())
    if missing:
        sys.exit(f"No photos in {dataset} for {missing}: they would disappear from recognition")
    for person in sorted(enrolled):
        folder = Path(dataset) / person
        vectors, problems = vectors_for(folder)
        if problems:
            sys.exit(f"{person}: {problems}")
        save(folder, person, vectors.values())
    number = build(client, dataset, alias)
    client.load_collection(f"{alias}_v{number}")  # before the rename, so the app is without a collection only briefly
    client.rename_collection(alias, f"{alias}_v0")  # kept as it was, for a rollback with `use 0`
    use(client, alias, number)


def show(alias=MILVUS_COLLECTION_NAME):
    client = connect()
    serving = in_use(client, alias)
    for number in versions(client.list_collections(), alias):
        name = f"{alias}_v{number}"
        print(f"{name}  {client.get_collection_stats(name)['row_count']} rows{'  (in use)' if name == serving else ''}")


def demo():
    with tempfile.TemporaryDirectory() as dataset:
        rng = np.random.default_rng(0)
        enrolled = {"alice": rng.standard_normal((5, 512)), "bob": rng.standard_normal((10, 512))}
        for person, vectors in enrolled.items():
            (Path(dataset) / person).mkdir()
            save(Path(dataset) / person, person, vectors)
        (Path(dataset) / "carol").mkdir()  # photos only, not enrolled yet
        names, vectors = load(dataset)
        assert names == ["alice"] * 5 + ["bob"] * 10, names
        assert np.array_equal(np.array(vectors), np.concatenate(list(enrolled.values())).astype(np.float32))
        assert load(Path(dataset) / "carol") == ([], [])
    assert versions(["F_v2", "F_v10", "F", "F_v1x", "G_v3", "F_v0"], "F") == [0, 2, 10]
    assert departments_of([("a", " Stores ", ["dispatch", "stores", " "]), ("b", None, []), ("c", "", ["All"])]) ==         {"a": ["dispatch", "stores"], "b": [], "c": ["all"]}
    from milvus_server import search_by_department

    class Collection:  # one search per department, results back in face order, a failure leaves faces unmatched
        searches = []

        def search(self, data, expr, **_):
            if "broken" in expr:
                raise RuntimeError("no departments field")
            self.searches.append(expr)
            return [[f"{expr or 'everyone'}:{face}"] for face in data]

    hits = search_by_department(Collection(), ["f0", "f1", "f2", "f3"], ["stores", "", "stores", "broken"])
    assert hits == [['array_contains_any(departments, ["stores", "all"]):f0'], ["everyone:f1"],
                    ['array_contains_any(departments, ["stores", "all"]):f2'], []], hits
    assert sorted(Collection.searches) == ["", 'array_contains_any(departments, ["stores", "all"])'], Collection.searches
    print("face_vectors demo: all checks passed")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "use" and len(sys.argv) == 3:
        client = connect()
        refuse_unless_migrated(client, MILVUS_COLLECTION_NAME)
        use(client, MILVUS_COLLECTION_NAME, int(sys.argv[2]))
    elif command == "publish":
        publish()
    elif command == "migrate":
        migrate()
    elif command == "list":
        show()
    elif command == "demo":
        demo()
    else:
        sys.exit(__doc__)
