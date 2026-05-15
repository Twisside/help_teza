from abc import ABC, abstractmethod
from sentence_transformers import SentenceTransformer


class EmbeddingService(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        pass


class GemmaEmbeddingService(EmbeddingService):
    def __init__(self, model_name="google/embeddinggemma-300m", device="cpu"):
        # Note: Gemma-300M might require a HuggingFace login (token)
        # to download due to its license.
        self.model = SentenceTransformer(model_name, device=device)
        self._dim = 768  # Default dimension for Gemma-300M

    def embed_text(self, text: str, is_query: bool = True) -> list[float]:
        # Gemma uses 'Retrieval-query' for searching and 'STS' for indexing
        task = "Retrieval-query" if is_query else "STS"
        return self.model.encode(text, prompt_name=task).tolist()

    @property
    def dimension(self) -> int:
        return self._dim


class QwenEmbeddingService(EmbeddingService):
    def __init__(self, model_name="Qwen/Qwen3-Embedding-0.6B", device="cpu"):
        self.model = SentenceTransformer(model_name, device=device)
        self._dim = 1024  # Default dimension for Qwen3-0.6B

    def embed_text(self, text: str, is_query: bool = True) -> list[float]:
        # Qwen performs better if you explicitly label queries
        prefix = "Query: " if is_query else "Document: "
        full_text = f"{prefix}{text}"
        return self.model.encode(full_text).tolist()

    @property
    def dimension(self) -> int:
        return self._dim