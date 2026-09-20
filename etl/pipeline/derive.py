from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from etl.core.paths import derived_dir, load_config
from etl.pipeline.gloss import index_glosses
from etl.pipeline.reduce import allowed_languages, load_raw_edges, reduce_edges

log = logging.getLogger(__name__)


def derived_edges_path() -> Path:
    return derived_dir() / "edges.parquet"


def derived_gloss_path() -> Path:
    return derived_dir() / "gloss_index.json"


def derived_lemma_path() -> Path:
    return derived_dir() / "lemma_index.json"


def derived_etym_parents_path() -> Path:
    return derived_dir() / "etym_parents.json"


def derived_meta_path() -> Path:
    return derived_dir() / "meta.json"


def derived_ready() -> bool:
    return derived_edges_path().exists() and derived_gloss_path().exists()


def rebuild_derived(cfg: dict[str, Any] | None = None) -> None:
    cfg = cfg or load_config()
    dest = derived_dir()
    dest.mkdir(parents=True, exist_ok=True)
    langs = allowed_languages(cfg)
    glosses, lemmas, parents = index_glosses(langs=langs)
    df = reduce_edges(load_raw_edges(), cfg, parents=parents)
    df.to_parquet(derived_edges_path(), index=False)
    derived_gloss_path().write_text(json.dumps(glosses, ensure_ascii=False) + "\n", encoding="utf-8")
    derived_lemma_path().write_text(json.dumps(lemmas, ensure_ascii=False) + "\n", encoding="utf-8")
    derived_etym_parents_path().write_text(
        json.dumps(parents, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    meta = {
        "n_edges": int(len(df)),
        "n_glosses": len(glosses),
        "n_lemmas": len(lemmas),
        "n_etym_parents": len(parents),
        "reltypes": df["reltype"].value_counts().to_dict() if len(df) else {},
        "langs": df["lang"].value_counts().to_dict() if len(df) else {},
    }
    derived_meta_path().write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    log.info("wrote derived artifacts to %s", dest)


def load_derived_edges() -> pd.DataFrame:
    path = derived_edges_path()
    if not path.exists():
        raise SystemExit("derived edges missing. Run: etl refresh")
    return pd.read_parquet(path)


def load_gloss_index() -> dict[str, str]:
    path = derived_gloss_path()
    if not path.exists():
        raise SystemExit("derived gloss index missing. Run: etl refresh")
    return json.loads(path.read_text(encoding="utf-8"))


def load_lemma_index() -> dict[str, str]:
    path = derived_lemma_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_etym_parents() -> dict[str, list[str]]:
    path = derived_etym_parents_path()
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): [str(t) for t in v] for k, v in raw.items()}
