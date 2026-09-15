from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from etl.paths import derived_dir, load_config, raw_dir

log = logging.getLogger(__name__)

EDGE_COLUMNS = ["term", "lang", "reltype", "related_term", "related_lang"]
MAX_TERM_LENGTH = 80


def is_junk_term(term: Any) -> bool:
    if term is None or (isinstance(term, float) and pd.isna(term)):
        return True
    s = str(term).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return True
    if s.startswith("-") or s.endswith("-"):
        return True
    if " " in s and not s.startswith("*"):
        return True
    if len(s) > MAX_TERM_LENGTH:
        return True
    if re.search(r"[\\/|]", s):
        return True
    return False


def allowed_languages(cfg: dict[str, Any]) -> set[str]:
    leaves = set(cfg["leaf_languages"].keys())
    ancestors = set(cfg.get("ancestor_languages") or [])
    return leaves | ancestors


def load_raw_edges(raw: Path | None = None) -> pd.DataFrame:
    raw = raw or raw_dir()
    parquet = raw / "etymology.parquet"
    jsonl = raw / "etymology.jsonl"
    if parquet.exists():
        df = pd.read_parquet(parquet)
    elif jsonl.exists():
        df = pd.read_json(jsonl, lines=True)
    else:
        raise SystemExit(
            f"no etymology dump in {raw} (expected etymology.parquet or etymology.jsonl). Run: etl refresh"
        )
    missing = [c for c in EDGE_COLUMNS if c not in df.columns]
    if missing:
        raise SystemExit(f"etymology dump missing columns: {missing}")
    return df[EDGE_COLUMNS]


def reduce_edges(df: pd.DataFrame, cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    cfg = cfg or load_config()
    langs = allowed_languages(cfg)
    reltypes = set(cfg["keep_reltypes"])
    out = df.copy()
    for col in EDGE_COLUMNS:
        out[col] = out[col].where(out[col].notna(), None)
    before = len(out)
    out = out[out["reltype"].isin(reltypes)]
    dropped_rel = before - len(out)
    mask_junk = out["term"].map(is_junk_term) | out["related_term"].map(is_junk_term)
    dropped_junk = int(mask_junk.sum())
    out = out.loc[~mask_junk]
    mask_lang = out["lang"].isin(langs) & out["related_lang"].isin(langs)
    dropped_lang = int((~mask_lang).sum())
    out = out.loc[mask_lang]
    out = out.drop_duplicates(subset=EDGE_COLUMNS)
    log.info(
        "reduce_edges: in=%s drop_reltype=%s drop_junk=%s drop_lang=%s out=%s",
        before,
        dropped_rel,
        dropped_junk,
        dropped_lang,
        len(out),
    )
    return out.reset_index(drop=True)


def first_gloss(obj: dict[str, Any]) -> str | None:
    for sense in obj.get("senses") or []:
        glosses = sense.get("glosses") or sense.get("raw_glosses") or []
        if glosses:
            g = str(glosses[0]).strip()
            if g:
                return g
    return None


def iter_gloss_files(raw: Path | None = None) -> Iterable[Path]:
    raw = raw or raw_dir()
    yield from sorted(raw.glob("kaikki*.jsonl"))
    extra = raw / "glosses.jsonl"
    if extra.exists():
        yield extra


def index_glosses(raw: Path | None = None, langs: set[str] | None = None) -> dict[str, str]:
    index: dict[str, str] = {}
    n_lines = 0
    for path in iter_gloss_files(raw):
        log.info("indexing glosses %s", path.name)
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                n_lines += 1
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                lang = obj.get("lang")
                word = obj.get("word")
                if not lang or not word:
                    continue
                if langs is not None and lang not in langs:
                    continue
                gloss = first_gloss(obj)
                if not gloss:
                    continue
                key = f"{lang}\t{word}"
                index.setdefault(key, gloss)
    log.info("gloss_index: lines=%s unique=%s", n_lines, len(index))
    return index


def gloss_for(index: dict[str, str], lang: str, term: str) -> str | None:
    return index.get(f"{lang}\t{term}")


def derived_edges_path() -> Path:
    return derived_dir() / "edges.parquet"


def derived_gloss_path() -> Path:
    return derived_dir() / "gloss_index.json"


def derived_meta_path() -> Path:
    return derived_dir() / "meta.json"


def derived_ready() -> bool:
    return derived_edges_path().exists() and derived_gloss_path().exists()


def rebuild_derived(cfg: dict[str, Any] | None = None) -> None:
    cfg = cfg or load_config()
    dest = derived_dir()
    dest.mkdir(parents=True, exist_ok=True)
    df = reduce_edges(load_raw_edges(), cfg)
    df.to_parquet(derived_edges_path(), index=False)
    langs = allowed_languages(cfg)
    glosses = index_glosses(langs=langs)
    derived_gloss_path().write_text(json.dumps(glosses, ensure_ascii=False) + "\n", encoding="utf-8")
    meta = {
        "n_edges": int(len(df)),
        "n_glosses": len(glosses),
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
