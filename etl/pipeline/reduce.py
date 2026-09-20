from __future__ import annotations

import logging
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from etl.core.paths import load_config, raw_dir
from etl.pipeline.gloss import LATIN_FAMILY_LANGS, fold_macrons

log = logging.getLogger(__name__)

EDGE_COLUMNS = ["term", "lang", "reltype", "related_term", "related_lang"]
MAX_TERM_LENGTH = 80


def _folded_term_key(term: Any) -> str:
    return fold_macrons(str(term)).casefold()


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


def reduce_edges(
    df: pd.DataFrame,
    cfg: dict[str, Any] | None = None,
    parents: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    cfg = cfg or load_config()
    langs = allowed_languages(cfg)
    reltypes = set(cfg["keep_reltypes"])
    ancestor_reltypes = set(cfg.get("ancestor_reltypes") or [])
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

    # Drop leaf→leaf ancestor hops when the terms differ (compound/component edges
    # like hipoxia→oxygen). Same-term loans (panel→panel) stay.
    dropped_leaf_hop = 0
    leaf_langs = set(cfg["leaf_languages"].keys())
    if ancestor_reltypes and leaf_langs and not out.empty:
        is_anc = out["reltype"].isin(ancestor_reltypes)
        both_leaf = out["lang"].isin(leaf_langs) & out["related_lang"].isin(leaf_langs)
        term_key = out["term"].map(_folded_term_key)
        related_key = out["related_term"].map(_folded_term_key)
        mask_cross = is_anc & both_leaf & (term_key != related_key)
        dropped_leaf_hop = int(mask_cross.sum())
        if dropped_leaf_hop:
            out = out.loc[~mask_cross]

    out, drop_align, align_fallback = _align_ancestor_edges(out, parents, ancestor_reltypes)
    log.info(
        "reduce_edges: in=%s drop_reltype=%s drop_junk=%s drop_lang=%s drop_leaf_hop=%s "
        "drop_etym_align=%s etym_align_fallback=%s out=%s",
        before,
        dropped_rel,
        dropped_junk,
        dropped_lang,
        dropped_leaf_hop,
        drop_align,
        align_fallback,
        len(out),
    )
    return out.reset_index(drop=True)



def _folded_term_set(terms: Iterable[str]) -> set[str]:
    return {fold_macrons(str(t)) for t in terms if t}


def _build_ancestor_successors(
    anc: pd.DataFrame,
) -> dict[tuple[str, str], list[tuple[str, str]]]:
    """Map (lang, term) → out-neighbors under ancestor edges."""
    succ: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    seen: set[tuple[str, str, str, str]] = set()
    for row in anc.itertuples(index=False):
        src = (str(row.lang), str(row.term))
        dst = (str(row.related_lang), str(row.related_term))
        key = (*src, *dst)
        if key in seen:
            continue
        seen.add(key)
        succ[src].append(dst)
    return succ


def _build_latin_family_aliases(
    anc: pd.DataFrame,
) -> dict[str, list[tuple[str, str]]]:
    """Map macron-folded term → Latin-family (lang, term) nodes in the ancestor graph."""
    aliases: dict[str, list[tuple[str, str]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for row in anc.itertuples(index=False):
        for lang, term in (
            (str(row.lang), str(row.term)),
            (str(row.related_lang), str(row.related_term)),
        ):
            if lang not in LATIN_FAMILY_LANGS:
                continue
            node = (lang, term)
            if node in seen:
                continue
            seen.add(node)
            aliases[fold_macrons(term)].append(node)
    return aliases


def _reaches_allowlisted(
    start_lang: str,
    start_term: str,
    allow_folded: set[str],
    successors: dict[tuple[str, str], list[tuple[str, str]]],
    latin_aliases: dict[str, list[tuple[str, str]]] | None = None,
) -> bool:
    """True when ``start`` or a dump-ancestor descendant has an allowlisted term (macron-folded).

    Latin-family nodes with the same folded spelling share successor walks so
    ``Late Latin:apostrŏphus`` can reach Greek via ``Latin:apostrophus``.
    """
    if fold_macrons(start_term) in allow_folded:
        return True
    start = (start_lang, start_term)
    seen: set[tuple[str, str]] = {start}
    q: deque[tuple[str, str]] = deque([start])
    latin_aliases = latin_aliases or {}

    def _expand_from(node: tuple[str, str]) -> Iterable[tuple[str, str]]:
        yield node
        if node[0] not in LATIN_FAMILY_LANGS:
            return
        for alias in latin_aliases.get(fold_macrons(node[1]), ()):
            if alias != node:
                yield alias

    while q:
        node = q.popleft()
        for base in _expand_from(node):
            if base not in seen and base != node:
                seen.add(base)
            for nxt in successors.get(base, ()):
                if nxt in seen:
                    continue
                if fold_macrons(nxt[1]) in allow_folded:
                    return True
                seen.add(nxt)
                q.append(nxt)
    return False


def _align_ancestor_edges(
    df: pd.DataFrame,
    parents: dict[str, list[str]] | None,
    ancestor_reltypes: set[str],
) -> tuple[pd.DataFrame, int, int]:
    """Drop ancestor edges outside the winning-gloss etymon family.

    Keep an edge when its ``related_term`` matches the allowlist (macron-folded)
    or when a dump-ancestor walk from that related node reaches an allowlisted
    parent (so Latin intermediates stay when templates only name Greek).

    If filtering would remove every ancestor edge for a source term, keep the
    original ancestor edges for that term (template/dump spelling miss).
    Non-ancestor reltypes are never filtered.
    """
    if not parents or df.empty or not ancestor_reltypes:
        return df, 0, 0
    allow = {k: set(v) for k, v in parents.items() if v}
    if not allow:
        return df, 0, 0
    is_anc = df["reltype"].isin(ancestor_reltypes)
    if not bool(is_anc.any()):
        return df, 0, 0
    keys = df["lang"].astype(str) + "\t" + df["term"].astype(str)
    keep_idx: list[Any] = list(df.index[~is_anc])
    dropped = 0
    fallback = 0
    anc = df.loc[is_anc]
    successors = _build_ancestor_successors(anc)
    latin_aliases = _build_latin_family_aliases(anc)
    grouped = anc.groupby(keys.loc[is_anc], sort=False)
    for key, grp in grouped:
        terms = allow.get(str(key))
        if not terms:
            keep_idx.extend(grp.index)
            continue
        allow_folded = _folded_term_set(terms)
        keep_rows: list[Any] = []
        for idx, row in grp.iterrows():
            related_term = str(row["related_term"])
            related_lang = str(row["related_lang"])
            if fold_macrons(related_term) in allow_folded or _reaches_allowlisted(
                related_lang,
                related_term,
                allow_folded,
                successors,
                latin_aliases,
            ):
                keep_rows.append(idx)
        if keep_rows:
            dropped += len(grp) - len(keep_rows)
            keep_idx.extend(keep_rows)
        else:
            fallback += 1
            keep_idx.extend(grp.index)
    return df.loc[keep_idx], dropped, fallback


