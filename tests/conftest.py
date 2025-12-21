"""Shared test fixtures for lance-code-rag."""

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from lance_code_rag import LCR_DIR
from lance_code_rag.config import LCRConfig, save_config
from lance_code_rag.manifest import create_empty_manifest, save_manifest


@pytest.fixture
def cli_runner():
    """Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_project():
    """Path to the fixture sample project."""
    return Path(__file__).parent / "fixtures" / "sample_project"


def setup_lcr_project(project_root: Path, config: LCRConfig | None = None) -> LCRConfig:
    """Initialize an lcr project at the given path.

    This replaces CLI-based initialization for testing.

    Args:
        project_root: Path to the project root
        config: Optional config to use (defaults to local embeddings)

    Returns:
        The config that was saved
    """
    if config is None:
        config = LCRConfig(
            embedding_provider="local",
            embedding_model="BAAI/bge-small-en-v1.5",
            embedding_dimensions=384,
        )

    # Create lcr directory
    lcr_dir = project_root / LCR_DIR
    lcr_dir.mkdir(parents=True, exist_ok=True)

    # Save config
    save_config(config, project_root)

    # Create empty manifest
    manifest = create_empty_manifest()
    save_manifest(manifest, project_root)

    return config


@pytest.fixture
def initialized_project(tmp_path: Path) -> Path:
    """A temporary project with lcr initialized (no indexing)."""
    setup_lcr_project(tmp_path)
    return tmp_path


@pytest.fixture
def indexed_project(tmp_path: Path, sample_project: Path) -> Path:
    """A temporary project with sample code indexed.

    Copies sample_project to tmp_path, initializes, and indexes.
    """
    from lance_code_rag.indexer import run_index

    # Copy sample project
    project = tmp_path / "project"
    shutil.copytree(sample_project, project)

    # Initialize
    setup_lcr_project(project)

    # Index
    run_index(project, force=False, verbose=False)

    return project
