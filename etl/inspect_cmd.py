from __future__ import annotations

from etl.models import Puzzle


def format_puzzle(p: Puzzle) -> str:
    lines = [
        f"id: {p.id}",
        f"enabled: {p.enabled}",
        f"lang_pair: {p.lang_pair}",
        f"quality_score: {p.quality_score}",
        f"source: {p.source}",
        "leaves:",
        f"  {p.leaf_a.get('lang')} {p.leaf_a.get('term')} - {p.leaf_a.get('gloss')}",
        f"  {p.leaf_b.get('lang')} {p.leaf_b.get('term')} - {p.leaf_b.get('gloss')}",
    ]
    if p.lca:
        lines.append(f"lca: {p.lca.get('lang')} {p.lca.get('term')} - {p.lca.get('gloss')}")
    lines.append("choices:")
    for c in p.choices:
        mark = "x" if c.get("id") == p.correct_choice else " "
        lines.append(f"  [{mark}] {c.get('id')}: {c.get('gloss')}")
    lines.append("gold edges:")
    for e in p.answer_graph.get("edges") or []:
        rel = f" ({e['reltype']})" if e.get("reltype") else ""
        lines.append(f"  {e.get('from')} -> {e.get('to')}{rel}")
    lines.append("nodes:")
    for n in p.answer_graph.get("nodes") or []:
        lines.append(f"  [{n.get('role')}] {n.get('id')}")
    return "\n".join(lines)
