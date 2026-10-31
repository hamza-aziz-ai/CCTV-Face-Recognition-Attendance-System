"""
This module is created to connect to milvus vector database service and store the embeddings which will then be
retrieved to compare them with the live stream face embeddings for facial recognition software

Reference: https://github.com/milvus-io/milvus

Date: 7 August 2023
Script Template Creator: Anubhav Patrick
Authors: Hamza Aziz and Kshitij Parashar
"""

# Import Dependencies
from pymilvus import (
    MilvusClient,
    connections,
    db,
    utility,
    FieldSchema, CollectionSchema, DataType,
    Collection
)

from custom_logging import multicam_server_logger, dynamic_face_data_collector_logger
from parameters import MILVUS_HOST, MILVUS_PORT, METRIC_TYPE, INDEX_TYPE, MILVUS_DATABASE
from parameters import MILVUS_STAGING_COLLECTION_NAME, LEGACY_SHARED_SERVICES, milvus_login


def milvus_token():
    """This client's Milvus login for MilvusClient; Milvus ignores it while authentication is off (legacy owner)."""
    user, password = milvus_login()
    return f"{user}:{password}" if user else "root:Milvus"


# PART 1: CONNECTING TO MILVUS
def create_connection(host: str = MILVUS_HOST, port: str = MILVUS_PORT):
    try:
        if LEGACY_SHARED_SERVICES:
            # Until the owner's cutover the app creates its own database; after it, deploy/provision.py does (D-037)
            connections.connect("setup", host=host, port=port)
            if MILVUS_DATABASE not in db.list_database(using="setup"):
                db.create_database(MILVUS_DATABASE, using="setup")
            connections.disconnect("setup")
        user, password = milvus_login()
        # Bound to the client's database at connect, so a failure leaves no connection rather than one to another database
        connections.connect("default", host=host, port=port, db_name=MILVUS_DATABASE, user=user, password=password)
        multicam_server_logger.info("Successfully connected to Milvus Server")
    except Exception as exception:
        multicam_server_logger.error(f"Error connecting to Milvus server due to exception: {exception}")


# PART 2: CREATE COLLECTION
def create_collection(collection_name: str = "Embeddings_Collection"):
    if utility.has_collection(collection_name):
        multicam_server_logger.info(f"Collection {collection_name} already exists.")
        return ensure_index(Collection(collection_name))

    fields = [
        FieldSchema(name="name_id", dtype=DataType.VARCHAR, is_primary=True, max_length=60, description="Unique ID of an individual"),
        FieldSchema(name="embeddings", dtype=DataType.FLOAT_VECTOR, dim=512, description="Face vector of an individual")
    ]
    schema = CollectionSchema(fields=fields, collection_name=collection_name)

    embeddings_collection = Collection(name=collection_name, schema=schema)
    multicam_server_logger.info(f"Collection '{collection_name}' created successfully.")

    return ensure_index(embeddings_collection)


def ensure_index(collection: Collection):
    # load() fails with "index not found" until an index exists, so an empty collection needs one too
    if collection.has_index():
        return collection

    # We are going to create an IVF_FLAT index for hello_milvus collection.
    # create_index() can only be applied to `FloatVector` and `BinaryVector` fields.
    multicam_server_logger.info(f"Start Creating index {INDEX_TYPE} for metric type {METRIC_TYPE}")
    index = {
        "index_type": INDEX_TYPE,
        "metric_type": METRIC_TYPE,
        "params": {"nlist": 128}
    }

    collection.create_index("embeddings", index)
    return collection


# PART 3: INSERTING DATA
def insert_data(collection: Collection, entities: list):
    collection.insert(data=entities)

    collection.flush()

    # print(collection_name.num_entities)

    print(f"Embeddings successfully inserted and the length is {collection.num_entities}")
    multicam_server_logger.info(f"Embeddings successfully inserted and the length is {collection.num_entities}")


# PART 4: SEARCHING THE CURRENT (DESIRED) EMBEDDING FROM THE EMBEDDING DATABASE
def search_embedding(collection: Collection, current_face_embeddings):
    vectors_to_search = current_face_embeddings
    search_params = {
        "metric_type": METRIC_TYPE,
        "params": {"nprobe": 10}
    }

    result = collection.search(
        data=vectors_to_search,
        anns_field="embeddings",
        param=search_params,
        limit=5,
        output_fields=["name_id"]
    )

    return result


# PART 5: DELETING A COLLECTION IF IT ALREADY EXISTS
def delete_collection(collection_name: str):
    if utility.has_collection(collection_name):
        # multicam_server_logger.warning(f"Collection {collection_name} already exists, so deleting it...")
        print(f"Collection {collection_name} already exists, so deleting it...")
        choice = input("Please enter your choice (Y for Yes, N for No): ")
        if choice in ["Yes", "Y"]:
            print("Collection deleted successfully.")
            multicam_server_logger.info("Collection deleted successfully.")
            utility.drop_collection(collection_name)
        else:
            print("User prompted to not to delete the collection.")
            multicam_server_logger.info("User prompted to not to delete the collection.")


# PART 6: DELETING A COLLECTION IF IT ALREADY EXISTS WITHOUT USER CONSENT
def delete_collection_without_consent(collection_name: str):
    if utility.has_collection(collection_name):
        dynamic_face_data_collector_logger.warning(f"Collection {collection_name} already exists, so deleting it...")
        try:
            utility.drop_collection(collection_name)
            dynamic_face_data_collector_logger.info("Collection deleted successfully.")
        except Exception as error:
            dynamic_face_data_collector_logger.error(f"Error in deleting collection due to: {error}.")


# PART 7: DELETE THE ENTITIES THAT ARE NO LONGER NEEDED BY FILTERING CONDITIONS OR THEIR PRIMARY KEYS
def delete_by_filter(person_id: str):
    client = MilvusClient(uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}", token=milvus_token(), db_name=MILVUS_DATABASE)
    deletion_result = client.delete(
        collection_name=MILVUS_STAGING_COLLECTION_NAME,
        filter=f"name_id in ['{person_id}']"
    )
    print(deletion_result)


if __name__ == "__main__":
    import sys
    print(delete_by_filter(sys.argv[1]))