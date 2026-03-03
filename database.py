import uuid
from abc import ABC, abstractmethod
from pymongo import MongoClient
from qdrant_client import QdrantClient
from qdrant_client.http import models
from embedding import EmbeddingService, QwenEmbeddingService, GemmaEmbeddingService
import os
from dotenv import load_dotenv
import os

load_dotenv()  # Loads variables from .env
os.environ["HF_TOKEN"] = os.getenv("HF_TOKEN")

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

    @abstractmethod
    def update(self, collection, item_id, new_data):
        pass

    @abstractmethod
    def delete(self, collection, item_id):
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

    def update(self, collection, item_id, new_data):
        from bson.objectid import ObjectId
        db = self.client.get_database()
        return db[collection].update_one({"_id": ObjectId(item_id)}, {"$set": new_data})

    def delete(self, collection, item_id):
        from bson.objectid import ObjectId
        db = self.client.get_database()
        return db[collection].delete_one({"_id": ObjectId(item_id)})


##    ==================================== MAIN QDRANT ===========================================


class QdrantRepo(DatabaseInterface):
    def __init__(self, use_qwen: bool = True, storage_path="./db/qdrant_data", device="cpu"):
        self.path = storage_path
        self.client = None
        self.device = device

        # Manual Switch Logic
        if use_qwen:
            print("Initializing Qwen3-Embedding-0.6B...")
            self.embedder = QwenEmbeddingService(device=self.device)
            self.collection_name = "user_entries_qwen"
        else:
            print("Initializing EmbeddingGemma-300M...")
            self.embedder = GemmaEmbeddingService(device=self.device)
            self.collection_name = "user_entries_gemma"


    def connect(self):
        self.client = QdrantClient(path=self.path)

        # Create a collection specific to the model's dimensions
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.embedder.dimension,
                    distance=models.Distance.COSINE
                ),
            )
        return self.client


    def insert(self, collection, data):
        # We override the 'collection' argument with our model-specific one
        target_col = self.collection_name

        text_to_embed = data.get("content", "")
        vector = self.embedder.embed_text(text_to_embed)

        point = models.PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload=data
        )

        return self.client.upsert(
            collection_name=target_col,
            points=[point]
        )


    def update(self, collection, item_id, new_data):
        target_col = self.collection_name

        if "content" in new_data:
            new_vector = self.embedder.embed_text(new_data["content"])
            return self.client.upsert(
                collection_name=target_col,
                points=[
                    models.PointStruct(
                        id=item_id,
                        vector=new_vector,
                        payload=new_data
                    )
                ]
            )

        return self.client.set_payload(
            collection_name=target_col,
            payload=new_data,
            points=[item_id]
        )


    def get_all(self, collection):
        points, _ = self.client.scroll(
            collection_name=self.collection_name,
            with_payload=True,
            with_vectors=False
        )
        return [{"id": p.id, **p.payload} for p in points]


    def delete(self, collection, item_id):
        return self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.PointIdsList(points=[item_id])
        )


    def search(self, collection, query_text, limit=5):
        """
        Searches for the most relevant items based on query_text.
        """
        # 1. Convert text to vector using the same embedder
        # For Qwen/Gemma, we typically use a 'Retrieval' prompt for searching
        query_vector = self.embedder.embed_text(query_text)

        # 2. Perform the vector search
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit,
            with_payload=True
        )

        # 3. Format the results nicely
        results = []
        for hit in response.points:
            results.append({
                "id": hit.id,
                "score": hit.score,  # How similar it is (closer to 1.0 is better)
                "payload": hit.payload
            })

        return results