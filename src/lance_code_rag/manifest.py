"""Manifest file management for Lance Code RAG."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import LCR_DIR, MANIFEST_FILE


class ManifestStats(BaseModel):
    """Statistics about the indexed codebase."""

    total_files: int = 0
    total_chunks: int = 0


class Manifest(BaseModel):
    """Manifest containing the Merkle tree and index metadata."""

    version: int = 1
    created_at: datetime
    updated_at: datetime
    tree: dict[str, Any] | None = None  # Merkle tree (None initially)
    stats: ManifestStats = Field(default_factory=ManifestStats)


def get_manifest_path(project_root: Path) -> Path:
    """Get the manifest file path."""
    return project_root / LCR_DIR / MANIFEST_FILE


def load_manifest(project_root: Path) -> Manifest | None:
    """Load manifest from the project's manifest file.

    Returns None if file doesn't exist.
    """
    manifest_path = get_manifest_path(project_root)

    if not manifest_path.exists():
        return None

    with open(manifest_path) as f:
        data = json.load(f)

    return Manifest.model_validate(data)


def save_manifest(manifest: Manifest, project_root: Path) -> None:
    """Save manifest to the project's manifest file."""
    manifest_path = get_manifest_path(project_root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    # Update the updated_at timestamp
    manifest.updated_at = datetime.now(UTC)

    with open(manifest_path, "w") as f:
        json.dump(manifest.model_dump(mode="json"), f, indent=2, default=str)


def create_empty_manifest() -> Manifest:
    """Create a new empty manifest."""
    now = datetime.now(UTC)
    return Manifest(
        created_at=now,
        updated_at=now,
        tree=None,
        stats=ManifestStats(),
    )
