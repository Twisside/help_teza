from datetime import datetime
import os
import uuid
from abc import ABC, abstractmethod
from dotenv import load_dotenv

from qdrant_client import QdrantClient
from qdrant_client.http import models
from embedding import LMSEmbeddingService



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



# class MongoRepo(DatabaseInterface):
#     def __init__(self, uri):
#         self.uri = uri
#         self.client = None
#
#     def connect(self):
#         self.client = MongoClient(self.uri)
#         return self.client
#
#     def insert(self, collection, data):
#         db = self.client.get_database()
#         return db[collection].insert_one(data)
#
#     def get_all(self, collection):
#         db = self.client.get_database()
#         return list(db[collection].find())
#
#     def update(self, collection, item_id, new_data):
#         from bson.objectid import ObjectId
#         db = self.client.get_database()
#         return db[collection].update_one({"_id": ObjectId(item_id)}, {"$set": new_data})
#
#     def delete(self, collection, item_id):
#         from bson.objectid import ObjectId
#         db = self.client.get_database()
#         return db[collection].delete_one({"_id": ObjectId(item_id)})
#

##    ==================================== MAIN QDRANT ===========================================


class QdrantRepo(DatabaseInterface):
    def __init__(self, use_qwen: bool = True, storage_path="./db/qdrant_data", device="cuda"):
        self.path = storage_path
        self.client = None
        self.device = device
        self.tag_collection = "global_tags"

        print("Initializing EmbeddingGemma-300M...")
        self.embedder = LMSEmbeddingService()
        self.collection_name = "user_entries_gemma_768" # Specific name for Gemma


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
        # Global Tag collection
        if not self.client.collection_exists(self.tag_collection):
            self.client.create_collection(
                collection_name=self.tag_collection,
                vectors_config=models.VectorParams(
                    size=self.embedder.dimension,
                    distance=models.Distance.COSINE
                )
            )
        return self.client


    def get_semantic_tags(self, text_embedding, threshold=0.8):
        """Finds existing tags that match the text context."""
        results = self.client.query_points(
            collection_name=self.tag_collection,
            query=text_embedding,
            limit=5,
            score_threshold=threshold
        )
        return [hit.payload['tag_name'] for hit in results.points]

    def add_new_tag(self, tag_name):
        """Adds a new tag string to the global registry."""
        vector = self.embedder.embed_text(tag_name)
        self.client.upsert(
            collection_name=self.tag_collection,
            points=[models.PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={"tag_name": tag_name}
            )]
)


    def insert(self, collection, data):
        target_col = self.collection_name
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        print(f"[{ts}] DB: Starting insert for file: {data.get('filename', 'unknown')}")

        if "timestamp" not in data:
            data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        text_to_embed = data.get("content", "")
        print(f"[{ts}] DB: Calling embed_text for: {data.get('filename', 'unknown')}")
        vector = self.embedder.embed_text(text_to_embed, is_query=False)
        print(f"[{ts}] DB: Embedding received for: {data.get('filename', 'unknown')}")

        point = models.PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload=data
        )
        result = self.client.upsert(collection_name=target_col, points=[point])
        print(f"[{ts}] DB: Upsert complete for: {data.get('filename', 'unknown')}")
        return result

    def update(self, collection, item_id, new_data):
        target_col = self.collection_name

        # --- NEW: Update Timestamp on edit ---
        new_data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if "content" in new_data:
            new_vector = self.embedder.embed_text(new_data["content"], is_query=False)
            return self.client.upsert(
                collection_name=target_col,
                points=[models.PointStruct(id=item_id, vector=new_vector, payload=new_data)]
            )

        return self.client.set_payload(collection_name=target_col, payload=new_data, points=[item_id])


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


    def search(self, collection, query_text, search_tags=None, limit=5):
        """
        Searches for the most relevant items based on query_text.
        Optionally filters the search by a list of tags.
        """
        query_vector = self.embedder.embed_text(query_text)

        query_filter = None
        if search_tags: # If search_tags is provided as a list (e.g., ["finance", "idea"])
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="tags", # Changed from 'tag' to 'tags'
                        match=models.MatchAny(any=search_tags)
                    )
                ]
            )

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True
        )

        results = []
        for hit in response.points:
            results.append({
                "id": hit.id,
                "score": hit.score,
                "payload": hit.payload
            })

        return results

    def search_conversation_archive(self, query_text, limit=5):
        """Search the conversation archive collection."""
        archive_collection = "conversation_archive"
        if not self.client.collection_exists(archive_collection):
            return []

        query_vector = self.embedder.embed_text(query_text)
        response = self.client.query_points(
            collection_name=archive_collection,
            query=query_vector,
            limit=limit,
            with_payload=True
        )

        results = []
        for hit in response.points:
            results.append({
                "id": hit.id,
                "score": hit.score,
                "payload": hit.payload
            })
        return results

    def insert_to_conversation_archive(self, content: str, role: str, turn_index: int, tags: list):
        """Insert a message into the conversation archive."""
        archive_collection = "conversation_archive"
        if not self.client.collection_exists(archive_collection):
            self.client.create_collection(
                collection_name=archive_collection,
                vectors_config=models.VectorParams(
                    size=self.embedder.dimension,
                    distance=models.Distance.COSINE
                ),
            )

        vector = self.embedder.embed_text(content, is_query=False)
        payload = {
            "content": content,
            "role": role,
            "turn_index": turn_index,
            "tags": tags,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        point = models.PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload=payload
        )
        return self.client.upsert(collection_name=archive_collection, points=[point])

    def clear_conversation_archive(self):
        """Delete all points from the conversation archive."""
        archive_collection = "conversation_archive"
        if self.client.collection_exists(archive_collection):
            self.client.delete(
                collection_name=archive_collection,
                points_selector=models.FilterSelector(
                    filter=models.Filter(must=[])
                )
            )
