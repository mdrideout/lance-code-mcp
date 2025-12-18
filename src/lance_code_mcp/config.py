"""Configuration management for Lance Code MCP."""

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from . import CONFIG_FILE, LCM_DIR


class LCMConfig(BaseModel):
    """Configuration for Lance Code MCP."""

    version: int = 1
    embedding_provider: Literal["local", "gemini", "openai"] = "local"
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dimensions: int = Field(default=768, ge=1)
    extensions: list[str] = Field(
        default=[".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp"]
    )
    exclude_patterns: list[str] = Field(
        default=[
            "node_modules",
            ".git",
            "__pycache__",
            "venv",
            ".venv",
            ".lance-code-mcp",
            "dist",
            "build",
            ".egg-info",
        ]
    )
    chunk_max_size: int = Field(default=2000, ge=100)
    chunk_overlap: int = Field(default=200, ge=0)
    watch_debounce_ms: int = Field(default=500, ge=100)


# Model configurations for each provider
EMBEDDING_MODELS = {
    "local": {
        "default": "BAAI/bge-base-en-v1.5",
        "dimensions": 768,
    },
    "gemini": {
        "default": "text-embedding-004",
        "dimensions": 768,
    },
    "openai": {
        "default": "text-embedding-3-small",
        "dimensions": 1536,
    },
}


def get_lcm_dir(project_root: Path) -> Path:
    """Get the .lance-code-mcp directory path."""
    return project_root / LCM_DIR


def get_config_path(project_root: Path) -> Path:
    """Get the config file path."""
    return get_lcm_dir(project_root) / CONFIG_FILE


def load_config(project_root: Path) -> LCMConfig:
    """Load configuration from the project's config file.

    Falls back to defaults if file doesn't exist.
    Environment variables can override config values.
    """
    config_path = get_config_path(project_root)

    if config_path.exists():
        with open(config_path) as f:
            data = json.load(f)
        config = LCMConfig.model_validate(data)
    else:
        config = LCMConfig()

    # Apply environment variable overrides
    config = _apply_env_overrides(config)

    return config


def save_config(config: LCMConfig, project_root: Path) -> None:
    """Save configuration to the project's config file."""
    config_path = get_config_path(project_root)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w") as f:
        json.dump(config.model_dump(), f, indent=2)


def create_default_config(
    embedding_provider: Literal["local", "gemini", "openai"] = "local",
) -> LCMConfig:
    """Create a default configuration with the specified embedding provider."""
    model_config = EMBEDDING_MODELS[embedding_provider]
    return LCMConfig(
        embedding_provider=embedding_provider,
        embedding_model=model_config["default"],
        embedding_dimensions=model_config["dimensions"],
    )


def _apply_env_overrides(config: LCMConfig) -> LCMConfig:
    """Apply environment variable overrides to config."""
    data = config.model_dump()

    # LCM_EMBEDDING_PROVIDER
    if provider := os.environ.get("LCM_EMBEDDING_PROVIDER"):
        if provider in ("local", "gemini", "openai"):
            data["embedding_provider"] = provider
            # Update model and dimensions for new provider
            model_config = EMBEDDING_MODELS[provider]
            data["embedding_model"] = model_config["default"]
            data["embedding_dimensions"] = model_config["dimensions"]

    # LCM_EMBEDDING_MODEL
    if model := os.environ.get("LCM_EMBEDDING_MODEL"):
        data["embedding_model"] = model

    return LCMConfig.model_validate(data)
