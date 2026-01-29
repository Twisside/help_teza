import uuid
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

    @abstractmethod
    def get_all(self, collection):
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

    def get_all(self, collection):
        db = self.client.get_database()
        return list(db[collection].find())


## ==================================== need to make implementation ===========================================
class QdrantRepo(DatabaseInterface):
    def __init__(self, storage_path="./db/qdrant_data"):
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
        # 1. Create a dummy vector of 4 floats (since size=4)
        # In a real app, you'd use an embedding model to turn text into these numbers
        dummy_vector = [0.1, 0.2, 0.3, 0.4]

        # 2. Qdrant needs a PointStruct
        point = models.PointStruct(
            id=str(uuid.uuid4()),  # Generates a unique ID
            vector=dummy_vector,
            payload=data  # This is where your dictionary {"content": "..."} goes
        )

        return self.client.upsert(
            collection_name=collection,
            points=[point]
        )

    def get_all(self, collection):
        # We scroll through points to get the 'payload' (your data)
        results, _ = self.client.scroll(collection_name=collection, with_payload=True)
        return [point.payload for point in results]