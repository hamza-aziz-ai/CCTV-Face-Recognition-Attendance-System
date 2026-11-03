"""Enrolment photos in this client's own MinIO bucket, <client>-enrolment, with its own access key (D-037, D-048).
Used by the API, which stores uploads, and by the enrolment worker, which reads, keeps or deletes them."""
import io
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from parameters import DATASET_STORE_ENDPOINT, ENROLMENT_BUCKET  # noqa: E402


class Store:
    def __init__(self):
        from minio import Minio  # imported here, so modules that only define jobs do not need it
        self.client = Minio(DATASET_STORE_ENDPOINT, access_key=os.getenv("STORE_APP_ACCESS_KEY", ""),
                            secret_key=os.getenv("STORE_APP_SECRET_KEY", ""), secure=False)
        self.bucket = ENROLMENT_BUCKET

    def put(self, key: str, data: bytes):
        self.client.put_object(self.bucket, key, io.BytesIO(data), len(data), content_type="image/jpeg")

    def get(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete(self, keys):
        for key in keys:
            self.client.remove_object(self.bucket, key)

    def list(self, prefix: str):
        return [item.object_name for item in self.client.list_objects(self.bucket, prefix=prefix, recursive=True)]


class MemoryStore:
    """For tests: the same three calls on a dict."""

    def __init__(self):
        self.objects = {}

    def put(self, key, data):
        self.objects[key] = bytes(data)

    def get(self, key):
        return self.objects[key]

    def delete(self, keys):
        for key in keys:
            self.objects.pop(key, None)

    def list(self, prefix):
        return sorted(key for key in self.objects if key.startswith(prefix))
