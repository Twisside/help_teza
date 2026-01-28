from abc import ABC, abstractmethod
from pymongo import MongoClient
from qdrant_client import QdrantClient
from qdrant_client.http import models


class DatabaseInterface(ABC):
    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def insert(self, collection, data):
        pass



class MongoRepo(DatabaseInterface):
    def __init__(self, uri):
        self.uri = uri
        self.client = None

    def connect(self):
        self.client = MongoClient(self.uri)
        return self.client

    def insert(self, collection, data):
        db = self.client.get_database()
        return db[collection].insert_one(data)


## ==================================== need to make implementation ===========================================
class QdrantRepo(DatabaseInterface):
    def __init__(self, storage_path="./qdrant_data"):
        self.path = storage_path
        self.client = None

    def connect(self):
        # This initializes the local on-disk DB
        self.client = QdrantClient(path=self.path)

        # Check if collection exists so we don't error out on restart
        collections = self.client.get_collections().collections
        exists = any(c.name == "user_entries" for c in collections)

        if not exists:
            self.client.create_collection(
                collection_name="user_entries",
                vectors_config=models.VectorParams(size=4, distance=models.Distance.COSINE),
            )
        return self.client

    def insert(self, collection, data):
        # Qdrant requires points/vectors; this is a simplified example
        return self.client.upsert(collection_name=collection, points=[data])