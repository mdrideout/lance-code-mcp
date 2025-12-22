"""Tests for init/remove wizard constants and inline prompt."""

from lance_code_rag.tui.app import LOCAL_MODELS, PROVIDERS


class TestProviders:
    """Tests for PROVIDERS configuration."""

    def test_has_three_providers(self):
        """Three provider options are available."""
        assert len(PROVIDERS) == 3

    def test_provider_structure(self):
        """Each provider has (id, display_text)."""
        for provider_id, display in PROVIDERS:
            assert isinstance(provider_id, str)
            assert isinstance(display, str)
            assert provider_id in ("local", "openai", "gemini")

    def test_local_is_first(self):
        """Local provider should be first (default)."""
        assert PROVIDERS[0][0] == "local"


class TestLocalModels:
    """Tests for LOCAL_MODELS configuration."""

    def test_has_three_models(self):
        """Three local model options are available."""
        assert len(LOCAL_MODELS) == 3

    def test_model_structure(self):
        """Each model has (id, display, model_name, dimensions)."""
        for model_id, display, model_name, dimensions in LOCAL_MODELS:
            assert isinstance(model_id, str)
            assert isinstance(display, str)
            assert model_name.startswith("BAAI/bge-")
            assert dimensions in (384, 768, 1024)

    def test_bge_base_is_recommended(self):
        """bge-base should be the recommended model."""
        displays = [display for _, display, _, _ in LOCAL_MODELS]
        recommended = [d for d in displays if "recommended" in d.lower()]
        assert len(recommended) == 1
        assert "bge-base" in recommended[0]

    def test_model_sizes_increasing(self):
        """Models are ordered from smallest to largest dimensions."""
        dimensions = [d for _, _, _, d in LOCAL_MODELS]
        assert dimensions == sorted(dimensions)
