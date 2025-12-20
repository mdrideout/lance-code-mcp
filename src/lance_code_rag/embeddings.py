"""Embedding providers for Lance Code RAG."""

from abc import ABC, abstractmethod

from .config import LCRConfig


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the embedding dimensions."""
        ...

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (same order as input)
        """
        ...

    def embed_single(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        return self.embed([text])[0]


class LocalEmbeddingProvider(EmbeddingProvider):
    """Local embedding using FastEmbed (ONNX-based, lightweight)."""

    # FastEmbed model name mapping
    MODEL_MAP = {
        # Map common names to FastEmbed model names
        "BAAI/bge-base-en-v1.5": "BAAI/bge-base-en-v1.5",
        "BAAI/bge-small-en-v1.5": "BAAI/bge-small-en-v1.5",
        "BAAI/bge-large-en-v1.5": "BAAI/bge-large-en-v1.5",
        # Default
        "bge-base": "BAAI/bge-base-en-v1.5",
        "bge-small": "BAAI/bge-small-en-v1.5",
    }

    DIMENSIONS = {
        "BAAI/bge-base-en-v1.5": 768,
        "BAAI/bge-small-en-v1.5": 384,
        "BAAI/bge-large-en-v1.5": 1024,
    }

    def __init__(self, model_name: str = "BAAI/bge-base-en-v1.5"):
        # Map to FastEmbed model name if needed
        self.model_name = self.MODEL_MAP.get(model_name, model_name)
        self._model = None  # Lazy loading

    @property
    def dimensions(self) -> int:
        """Return embedding dimensions for the model."""
        return self.DIMENSIONS.get(self.model_name, 384)

    def _load_model(self):
        """Lazy load the model on first use."""
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Batch embed texts using FastEmbed."""
        if not texts:
            return []

        self._load_model()
        # FastEmbed returns a generator, convert to list
        embeddings = list(self._model.embed(texts))
        return [emb.tolist() for emb in embeddings]


def get_embedding_provider(config: LCRConfig) -> EmbeddingProvider:
    """
    Factory function to get the appropriate embedding provider.

    Args:
        config: LCR configuration with provider settings

    Returns:
        An EmbeddingProvider instance

    Raises:
        ValueError: If provider is not supported (Phase 2 only supports local)
    """
    if config.embedding_provider == "local":
        return LocalEmbeddingProvider(config.embedding_model)
    else:
        raise ValueError(
            f"Provider '{config.embedding_provider}' not supported. "
            f"Phase 2 only supports 'local'. Cloud providers coming in Phase 6."
        )
