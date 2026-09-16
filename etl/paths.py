from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
FIXTURES_DIR = PACKAGE_DIR / "fixtures"


def config_path() -> Path:
    override = os.environ.get("ETL_CONFIG")
    if override:
        return Path(override)
    return PACKAGE_DIR / "config.yaml"


def data_dir() -> Path:
    override = os.environ.get("ETL_DATA_DIR")
    if override:
        return Path(override)
    return REPO_ROOT / "data"


def load_config(path: Path | None = None) -> dict[str, Any]:
    p = path or config_path()
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def raw_dir() -> Path:
    return data_dir() / "raw"


def derived_dir() -> Path:
    return data_dir() / "derived"


def puzzles_dir() -> Path:
    return data_dir() / "puzzles"


def reports_dir() -> Path:
    return data_dir() / "reports"


def default_puzzles_jsonl() -> Path:
    return puzzles_dir() / "puzzles.jsonl"


def database_url() -> str | None:
    env = os.environ.get("DATABASE_URL")
    if env and env.strip():
        return env.strip()
    try:
        cfg = load_config()
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(cfg, dict):
        return None
    value = cfg.get("database_url")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
