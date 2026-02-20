"""Configuration loading and path resolution."""

from __future__ import annotations

from pathlib import Path

import yaml

_DEFAULT_CONFIG = "config.yaml"


def load_config(config_path: str | None = None) -> dict:
    path = Path(config_path or _DEFAULT_CONFIG)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_project_root(config_path: str | None = None) -> Path:
    path = Path(config_path or _DEFAULT_CONFIG)
    return path.resolve().parent


def resolve_path(config: dict, key_path: str, config_path: str | None = None) -> Path:
    root = get_project_root(config_path)
    keys = key_path.split(".")
    val = config
    for k in keys:
        val = val[k]
    p = Path(val)
    if not p.is_absolute():
        p = root / p
    return p


def get_clips_dir(config: dict, config_path: str | None = None) -> Path:
    return resolve_path(config, "clips_dir", config_path)


def get_platforms(config: dict) -> list[str]:
    return config.get("platforms", [])
