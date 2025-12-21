"""Tests for the init wizard."""


from lance_code_rag.tui import WizardResult
from lance_code_rag.tui.init_wizard import LOCAL_MODELS


class TestWizardResult:
    """Tests for WizardResult dataclass."""

    def test_default_values(self):
        """WizardResult has sensible defaults."""
        result = WizardResult()
        assert result.provider == ""
        assert result.model == ""
        assert result.dimensions == 0
        assert result.cancelled is False

    def test_cancelled_result(self):
        """Cancelled result is properly flagged."""
        result = WizardResult(cancelled=True)
        assert result.cancelled is True
        assert result.provider == ""

    def test_complete_result(self):
        """Complete result contains all fields."""
        result = WizardResult(
            provider="local",
            model="BAAI/bge-base-en-v1.5",
            dimensions=768,
        )
        assert result.provider == "local"
        assert result.model == "BAAI/bge-base-en-v1.5"
        assert result.dimensions == 768
        assert result.cancelled is False


class TestLocalModels:
    """Tests for LOCAL_MODELS configuration."""

    def test_has_three_models(self):
        """Three local model options are available."""
        assert len(LOCAL_MODELS) == 3

    def test_model_structure(self):
        """Each model has (name, id, dimensions)."""
        for name, model_id, dimensions in LOCAL_MODELS:
            assert isinstance(name, str)
            assert "bge" in name.lower()
            assert model_id.startswith("BAAI/bge-")
            assert dimensions in (384, 768, 1024)

    def test_bge_base_is_recommended(self):
        """bge-base should be the recommended model."""
        names = [name for name, _, _ in LOCAL_MODELS]
        recommended = [n for n in names if "recommended" in n.lower()]
        assert len(recommended) == 1
        assert "bge-base" in recommended[0]

    def test_model_sizes_increasing(self):
        """Models are ordered from smallest to largest dimensions."""
        dimensions = [d for _, _, d in LOCAL_MODELS]
        assert dimensions == sorted(dimensions)
