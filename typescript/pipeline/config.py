"""Configuration loading and path resolution."""

from __future__ import annotations

from pathlib import Path

import yaml

from pipeline.models import LanguageConfig

_DEFAULT_CONFIG = "config.yaml"


def load_config(config_path: str | None = None) -> dict:
    """Load and validate the YAML configuration file.

    Args:
        config_path: Path to config.yaml. Defaults to ./config.yaml.

    Returns:
        Parsed config dict.

    Raises:
        FileNotFoundError: If config file doesn't exist.
    """
    path = Path(config_path or _DEFAULT_CONFIG)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_project_root(config_path: str | None = None) -> Path:
    """Return the project root (directory containing config.yaml)."""
    path = Path(config_path or _DEFAULT_CONFIG)
    return path.resolve().parent


def resolve_path(config: dict, key_path: str, config_path: str | None = None) -> Path:
    """Resolve a path from config relative to project root.

    Args:
        config: Parsed config dict.
        key_path: Dot-separated path into config (e.g. 'clips.output_dir').
        config_path: Path to config.yaml for resolving project root.

    Returns:
        Resolved absolute Path.
    """
    root = get_project_root(config_path)
    keys = key_path.split(".")
    val = config
    for k in keys:
        val = val[k]
    p = Path(val)
    if not p.is_absolute():
        p = root / p
    return p


def get_languages(config: dict) -> list[LanguageConfig]:
    """Parse language configs from config."""
    return [
        LanguageConfig(code=lang["code"], name=lang["name"])
        for lang in config.get("languages", [])
    ]


def get_clips_dir(config: dict, config_path: str | None = None) -> Path:
    """Get resolved clips output directory."""
    return resolve_path(config, "clips.output_dir", config_path)


def get_clips_status_path(config: dict, config_path: str | None = None) -> Path:
    """Get resolved clips status file path."""
    return resolve_path(config, "clips.status_file", config_path)


def get_images_dir(config: dict, config_path: str | None = None) -> Path:
    """Get resolved images input directory."""
    return resolve_path(config, "clips.images_dir", config_path)


def get_quotes_output_dir(config: dict, config_path: str | None = None) -> Path:
    """Get resolved quotes output directory."""
    return resolve_path(config, "assembly.output_dir", config_path)


def get_quotes_status_path(config: dict, config_path: str | None = None) -> Path:
    """Get resolved quotes status file path."""
    return resolve_path(config, "assembly.quotes_status_file", config_path)


def get_quotes_dir(config: dict, config_path: str | None = None) -> Path:
    """Get resolved quotes input directory."""
    return resolve_path(config, "quotes_dir", config_path)


def get_platforms(config: dict) -> list[str]:
    """Get configured platform names."""
    return config.get("platforms", [])
