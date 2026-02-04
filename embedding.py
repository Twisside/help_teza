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

    def embed_text(self, text: str, task_type="STS") -> list[float]:
        """
        Gemma uses specific prompt names:
        'STS' for similarity, 'Retrieval-query' for searching.
        """
        # Gemma models are designed to use prompt_name for best results
        embedding = self.model.encode(text, prompt_name=task_type)
        return embedding.tolist()

    @property
    def dimension(self) -> int:
        return self._dim


class QwenEmbeddingService(EmbeddingService):
    def __init__(self, model_name="Qwen/Qwen3-Embedding-0.6B", device="cpu"):
        self.model = SentenceTransformer(model_name, device=device)
        self._dim = 1024  # Default dimension for Qwen3-0.6B

    def embed_text(self, text: str, instruction: str = None) -> list[float]:
        """
        Qwen is instruction-aware.
        Example instruction: "Given a web search query, retrieve relevant passages."
        """
        if instruction:
            # Qwen typically expects the instruction prepended or via a prompt argument
            full_text = f"Instruct: {instruction}\nQuery: {text}"
        else:
            full_text = text

        embedding = self.model.encode(full_text)
        return embedding.tolist()

    @property
    def dimension(self) -> int:
        return self._dim