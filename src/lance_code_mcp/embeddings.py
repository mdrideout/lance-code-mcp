"""Embedding providers for Lance Code MCP."""

from abc import ABC, abstractmethod

from .config import LCMConfig


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
    """Local embedding using sentence-transformers."""

    def __init__(self, model_name: str = "BAAI/bge-base-en-v1.5"):
        self.model_name = model_name
        self._model = None  # Lazy loading
        self._dimensions: int | None = None

    @property
    def dimensions(self) -> int:
        """BGE-base has 768 dimensions."""
        if self._dimensions is not None:
            return self._dimensions
        # Default for BGE models
        if "bge-base" in self.model_name:
            return 768
        if "bge-small" in self.model_name:
            return 384
        if "bge-large" in self.model_name:
            return 1024
        # Fallback - load model to get dimensions
        self._load_model()
        return self._dimensions or 768

    def _load_model(self):
        """Lazy load the model on first use."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            self._dimensions = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Batch embed texts using sentence-transformers."""
        if not texts:
            return []

        self._load_model()
        embeddings = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()


def get_embedding_provider(config: LCMConfig) -> EmbeddingProvider:
    """
    Factory function to get the appropriate embedding provider.

    Args:
        config: LCM configuration with provider settings

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
