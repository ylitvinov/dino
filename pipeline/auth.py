"""Authentication for KIE.ai API.

KIE uses simple Bearer token authentication with an API key.
No JWT generation or token refresh needed.
"""

from __future__ import annotations

import yaml
from pathlib import Path


_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def get_api_key(config_path: str | Path | None = None) -> str:
    """Return the API key from config.yaml.

    Args:
        config_path: Override path to config file. Defaults to project root config.yaml.

    Returns:
        The API key string.

    Raises:
        FileNotFoundError: If config file does not exist.
        ValueError: If api_key is missing or still set to placeholder.
    """
    path = Path(config_path) if config_path else _CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    api_key: str = config.get("api", {}).get("api_key", "")
    if not api_key or api_key == "YOUR_KIE_API_KEY":
        raise ValueError(
            "API key not configured. Set 'api.api_key' in config.yaml "
            "with your KIE.ai API key."
        )
    return api_key


def get_auth_headers(config_path: str | Path | None = None) -> dict[str, str]:
    """Return authorization headers for KIE.ai API requests.

    Args:
        config_path: Override path to config file.

    Returns:
        Dict with Authorization header.
    """
    api_key = get_api_key(config_path)
    return {"Authorization": f"Bearer {api_key}"}


def load_config(config_path: str | Path | None = None) -> dict:
    """Load and return the full configuration dictionary.

    Args:
        config_path: Override path to config file.

    Returns:
        The parsed config dictionary.
    """
    path = Path(config_path) if config_path else _CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_output_paths(config: dict, scenario_path: str | None = None) -> dict:
    """Resolve output paths, scoping shots per scenario while sharing elements.

    Elements are always shared across scenarios.
    Shots and shot status are scoped to output/<scenario_stem>/.

    Returns dict with keys: elements_dir, elements_status_file, shots_dir, status_file.
    """
    base_dir = Path(config["output"].get("base_dir", "output"))
    elements_dir = Path(config["output"]["elements_dir"])
    elements_status_file = base_dir / "elements_status.json"

    if scenario_path:
        stem = Path(scenario_path).stem
        shots_dir = base_dir / stem / "shots"
        status_file = base_dir / stem / "status.json"
    else:
        shots_dir = base_dir / "shots"
        status_file = base_dir / "status.json"

    return {
        "elements_dir": elements_dir,
        "elements_status_file": elements_status_file,
        "shots_dir": shots_dir,
        "status_file": status_file,
    }
