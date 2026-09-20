from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from etl.core.paths import default_puzzles_jsonl, reports_dir
from etl.pipeline.derive import derived_meta_path, load_derived_edges, derived_ready
from etl.store.iojson import read_jsonl


def edge_stats() -> dict[str, Any]:
    if not derived_ready():
        return {"error": "derived artifacts missing"}
    df = load_derived_edges()
    by_rel = df["reltype"].value_counts().to_dict() if len(df) else {}
    by_lang = df["lang"].value_counts().to_dict() if len(df) else {}
    return {
        "n_edges": int(len(df)),
        "by_reltype": by_rel,
        "by_lang": by_lang,
    }


def puzzle_stats_from_file(path: Path | None = None) -> dict[str, Any]:
    path = path or default_puzzles_jsonl()
    if not path.exists():
        return {"n_puzzles": 0, "by_lang_pair": {}, "path": str(path)}
    puzzles = read_jsonl(path)
    pairs = Counter(p.lang_pair for p in puzzles)
    enabled = sum(1 for p in puzzles if p.enabled)
    return {
        "n_puzzles": len(puzzles),
        "enabled": enabled,
        "by_lang_pair": dict(pairs),
        "path": str(path),
    }


def load_funnel() -> dict[str, Any]:
    path = reports_dir() / "funnel.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def collect_stats(puzzle_path: Path | None = None) -> dict[str, Any]:
    meta = {}
    mp = derived_meta_path()
    if mp.exists():
        meta = json.loads(mp.read_text(encoding="utf-8"))
    payload = {
        "derived_meta": meta,
        "edges": edge_stats(),
        "puzzles": puzzle_stats_from_file(puzzle_path),
        "funnel": load_funnel(),
    }
    return payload
