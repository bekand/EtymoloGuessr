from __future__ import annotations

import hashlib
import json
from typing import Any


def content_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def puzzle_id(leaf_a: dict[str, Any], leaf_b: dict[str, Any], lca: dict[str, Any], edges: list[dict[str, Any]]) -> str:
    a, b = sorted([leaf_a, leaf_b], key=lambda x: (x["lang"], x["term"]))
    canon_edges = sorted(
        ({"from": e["from"], "to": e["to"]} for e in edges),
        key=lambda e: (e["from"], e["to"]),
    )
    return content_hash(
        {
            "leaf_a": {"lang": a["lang"], "term": a["term"]},
            "leaf_b": {"lang": b["lang"], "term": b["term"]},
            "lca": {"lang": lca["lang"], "term": lca["term"]},
            "edges": canon_edges,
        }
    )
