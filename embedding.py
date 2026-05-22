import requests
from abc import ABC, abstractmethod


class EmbeddingService(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        pass


class LMSEmbeddingService(EmbeddingService):
    def __init__(self, model_name="text-embedding-embeddinggemma-300m@q4_0", dimension=768, base_url="http://127.0.0.1:1234/v1"):
        """
        :param model_name: The identifier of the embedding model loaded in LM Studio.
        :param dimension: The output dimension of the model (must match your Qdrant collection).
        :param base_url: The URL where LM Studio is running.
        """
        self.model_name = model_name
        self._dim = dimension
        self.base_url = base_url

    def _ts(self):
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def embed_text(self, text: str, is_query: bool = True) -> list[float]:
        prefix = "search_query: " if is_query else "search_document: "
        full_text = f"{prefix}{text}"

        url = f"{self.base_url}/embeddings"
        payload = {
            "model": self.model_name,
            "input": full_text
        }

        try:
            print(f"[{self._ts()}] EMBED: Requesting embedding for text (len={len(text)})")
            response = requests.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            print(f"[{self._ts()}] EMBED: Received embedding response")
            return data['data'][0]['embedding']

        except requests.exceptions.RequestException as e:
            print(f"Error fetching embedding from LM Studio: {e}")
            raise e

    @property
    def dimension(self) -> int:
        return self._dim