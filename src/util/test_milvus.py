import os
import sys
import time
from pymilvus import connections, Collection, MilvusClient, utility

MILVUS_HOST = os.environ.get("MILVUS_HOST", "localhost")

try:
    connections.connect("default", host=MILVUS_HOST, port="19530")
    print("Connection Successful")
except Exception as e:
    print(f"Connection Failed due to {e}")

collection = Collection("FACE_DATA_STAGING_COLLECTION_FOR_COSINE")  # Get an existing collection.

person_id = sys.argv[1]  # usage: python test_milvus.py <PERSON_ID>

print(collection.schema)
samples = collection.query(output_fields=["name_id"], expr=f"name_id == '{person_id}'")
print("Sample PKs:", samples)
print(collection.num_entities)

delete_result = collection.delete(expr=f"name_id == '{person_id}'")
collection.flush()
print("DeleteResult:", delete_result)      # should include delete_count

collection.compact()
print("🔧 Compaction triggered")

collection.wait_for_compaction_completed()
print("✅ Compaction completed")


print("After delete, still found:", collection.query(expr=f"name_id == '{person_id}'", output_fields=["name_id"]))

time.sleep(60)

# 5) Release & reload so that num_entities drops deleted vectors
collection.release()
collection.load()

# 6) In-memory live count
print("Live entities (num_entities):", collection.num_entities)

# 7) Use MilvusClient to fetch row_count
client = MilvusClient(uri=f"http://{MILVUS_HOST}:19530")
stats = client.get_collection_stats(collection_name="FACE_DATA_STAGING_COLLECTION_FOR_COSINE")
print("Server row_count:", stats["row_count"])
