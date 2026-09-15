from __future__ import annotations

import json
import logging
import sys
import time
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Callable

import networkx as nx

from etl.derive import gloss_for, load_derived_edges, load_gloss_index
from etl.ids import puzzle_id
from etl.models import GraphEdge, GraphNode, Puzzle, node_id
from etl.paths import load_config, reports_dir

log = logging.getLogger(__name__)

STOPWORDS = {
    "a",
    "an",
    "the",
    "of",
    "to",
    "and",
    "or",
    "in",
    "on",
    "for",
    "with",
    "from",
    "by",
    "as",
    "is",
    "be",
}
MIN_TOKEN_LENGTH = 2


def tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    words = set()
    buf = []
    for ch in text.lower():
        if ch.isalnum():
            buf.append(ch)
        else:
            if buf:
                w = "".join(buf)
                if w not in STOPWORDS and len(w) >= MIN_TOKEN_LENGTH:
                    words.add(w)
                buf = []
    if buf:
        w = "".join(buf)
        if w not in STOPWORDS and len(w) >= MIN_TOKEN_LENGTH:
            words.add(w)
    return words


def gloss_overlap(a: str | None, b: str | None) -> float:
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def still_same_meaning(leaf_gloss: str | None, lca_gloss: str | None, max_overlap: float) -> bool:
    """True when a modern leaf still expresses the ancestor gloss (no semantic shift)."""
    if gloss_overlap(leaf_gloss, lca_gloss) >= max_overlap:
        return True
    leaf_tok, lca_tok = tokenize(leaf_gloss), tokenize(lca_gloss)
    if lca_tok and lca_tok <= leaf_tok:
        return True
    if leaf_tok and lca_tok and leaf_tok <= lca_tok:
        return True
    return False


def lang_pair_code(lang_a: str, lang_b: str, leaf_codes: dict[str, str]) -> str:
    ca, cb = leaf_codes[lang_a], leaf_codes[lang_b]
    return "-".join(sorted([ca, cb]))


def build_graph(edges, ancestor_reltypes: set[str]) -> nx.DiGraph:
    g = nx.DiGraph()
    for row in edges.itertuples(index=False):
        src = node_id(row.lang, row.term)
        dst = node_id(row.related_lang, row.related_term)
        g.add_node(src, lang=row.lang, term=row.term)
        g.add_node(dst, lang=row.related_lang, term=row.related_term)
        if row.reltype in ancestor_reltypes:
            g.add_edge(src, dst, reltype=row.reltype)
    return g


def ancestor_paths(g: nx.DiGraph, start: str, max_depth: int, ancestor_reltypes: set[str]) -> dict[str, list[str]]:
    paths: dict[str, list[str]] = {start: [start]}
    q: deque[tuple[str, int]] = deque([(start, 0)])
    while q:
        node, depth = q.popleft()
        if depth >= max_depth:
            continue
        for _, succ, data in g.out_edges(node, data=True):
            if data.get("reltype") not in ancestor_reltypes:
                continue
            if succ not in paths:
                paths[succ] = paths[node] + [succ]
                q.append((succ, depth + 1))
    return paths


def subgraph_from_paths(path_a: list[str], path_b: list[str]) -> list[str]:
    seen: list[str] = []
    for n in path_a + path_b:
        if n not in seen:
            seen.append(n)
    return seen


def quality_score(
    *,
    lang_a: str,
    lang_b: str,
    n_nodes: int,
    high_overlap: bool,
    lca_is_modern: bool,
    min_nodes: int = 3,
) -> int:
    """Integer 0-5. Cross-language pairs cannot fall below 1."""
    score = 5
    if lang_a == lang_b:
        score -= 2
    if {lang_a, lang_b} == {"Spanish", "Portuguese"}:
        score -= 1
    if lca_is_modern:
        score -= 1
    if high_overlap:
        score -= 1
    if n_nodes <= min_nodes:
        score -= 1
    return score


class Funnel:
    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def bump(self, reason: str, n: int = 1) -> None:
        self.counts[reason] += n

    def as_dict(self) -> dict[str, int]:
        return dict(self.counts)


class StageTimer:
    """Print timed stage progress to stderr when verbose is enabled."""

    def __init__(self, enabled: bool = False, stream=None) -> None:
        self.enabled = enabled
        self.stream = stream or sys.stderr
        self._t0 = time.perf_counter()
        self._last = self._t0

    def stage(self, name: str, detail: str = "") -> None:
        if not self.enabled:
            return
        now = time.perf_counter()
        stage_s = now - self._last
        total_s = now - self._t0
        suffix = f" ({detail})" if detail else ""
        print(
            f"[generate] {name}{suffix}: {stage_s:.3f}s (total {total_s:.3f}s)",
            file=self.stream,
            flush=True,
        )
        self._last = now


def _iter_related_leaf_pairs(
    leaves_with_gloss: list[str],
    paths_by_leaf: dict[str, dict[str, list[str]]],
) -> Any:
    """Yield each unordered leaf pair that shares at least one ancestor (once).

    Avoids the naive all-pairs O(L^2) walk when most leaves do not share ancestry.
    Worst case (one universal ancestor) is still O(L^2), but typical etymology
    graphs are much sparser.
    """
    by_ancestor: dict[str, list[str]] = defaultdict(list)
    for leaf_id in leaves_with_gloss:
        for anc in paths_by_leaf[leaf_id]:
            if anc != leaf_id:
                by_ancestor[anc].append(leaf_id)

    # Stable order: ancestors by descending fan-out then id; leaves sorted per bucket.
    ancestor_order = sorted(by_ancestor.keys(), key=lambda a: (-len(by_ancestor[a]), a))
    seen_pairs: set[tuple[str, str]] = set()
    for anc in ancestor_order:
        group = sorted(set(by_ancestor[anc]))
        for i, leaf_a_id in enumerate(group):
            for leaf_b_id in group[i + 1 :]:
                key = (leaf_a_id, leaf_b_id) if leaf_a_id < leaf_b_id else (leaf_b_id, leaf_a_id)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                yield leaf_a_id, leaf_b_id


def extract_candidates(
    g: nx.DiGraph,
    glosses: dict[str, str],
    cfg: dict[str, Any],
    funnel: Funnel,
    *,
    limit: int | None = None,
    min_quality: int = 0,
    progress: Callable[[str, str], None] | None = None,
) -> list[dict[str, Any]]:
    leaf_langs = cfg["leaf_languages"]
    ancestor_reltypes = set(cfg["ancestor_reltypes"])
    generation_config = cfg["generate"]
    min_nodes = int(generation_config["min_nodes"])
    max_nodes = int(generation_config["max_nodes"])
    max_depth = int(generation_config["max_ancestor_depth"])
    max_overlap = float(generation_config["max_gloss_overlap"])

    leaves = [n for n, data in g.nodes(data=True) if data.get("lang") in leaf_langs]
    leaves.sort()
    funnel.bump("leaves", len(leaves))
    if progress:
        progress("collect leaves", f"{len(leaves)} leaf nodes")

    paths_by_leaf: dict[str, dict[str, list[str]]] = {}
    leaves_with_gloss: list[str] = []
    gloss_cache: dict[str, str] = {}
    for n in leaves:
        lang = g.nodes[n]["lang"]
        term = g.nodes[n]["term"]
        gloss = gloss_for(glosses, lang, term)
        if not gloss:
            funnel.bump("no_gloss_leaf")
            continue
        gloss_cache[n] = gloss
        paths_by_leaf[n] = ancestor_paths(g, n, max_depth, ancestor_reltypes)
        leaves_with_gloss.append(n)
    if progress:
        progress(
            "ancestor paths",
            f"{len(leaves_with_gloss)} glossed leaves, {sum(len(p) for p in paths_by_leaf.values())} path entries",
        )

    candidates: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str, str]] = set()
    good_count = 0
    stop_at = None if not limit or limit <= 0 else limit

    for leaf_a_id, leaf_b_id in _iter_related_leaf_pairs(leaves_with_gloss, paths_by_leaf):
        funnel.bump("pairs_considered")
        lang_a = g.nodes[leaf_a_id]["lang"]
        term_a = g.nodes[leaf_a_id]["term"]
        gloss_a = gloss_cache[leaf_a_id]
        lang_b = g.nodes[leaf_b_id]["lang"]
        term_b = g.nodes[leaf_b_id]["term"]
        gloss_b = gloss_cache[leaf_b_id]
        paths_a = paths_by_leaf[leaf_a_id]
        paths_b = paths_by_leaf[leaf_b_id]
        common = (set(paths_a) & set(paths_b)) - {leaf_a_id, leaf_b_id}
        if not common:
            funnel.bump("no_lca")
            continue

        ranked = sorted(
            common,
            key=lambda node: (len(paths_a[node]) + len(paths_b[node]), len(paths_a[node])),
        )
        chosen = None
        node_list: list[str] = []
        path_a: list[str] = []
        path_b: list[str] = []
        for lca_node_id in ranked:
            nodes = subgraph_from_paths(paths_a[lca_node_id], paths_b[lca_node_id])
            if len(nodes) < min_nodes:
                continue
            if len(nodes) > max_nodes:
                continue
            chosen = lca_node_id
            node_list = nodes
            path_a = paths_a[lca_node_id]
            path_b = paths_b[lca_node_id]
            break
        if chosen is None:
            too_big = any(
                len(subgraph_from_paths(paths_a[lca_node_id], paths_b[lca_node_id])) > max_nodes
                for lca_node_id in ranked
            )
            funnel.bump("too_big" if too_big else "too_small")
            continue

        lca_lang = g.nodes[chosen]["lang"]
        lca_term = g.nodes[chosen]["term"]
        lca_gloss = gloss_for(glosses, lca_lang, lca_term)
        if not lca_gloss:
            funnel.bump("no_gloss")
            continue

        if still_same_meaning(gloss_a, lca_gloss, max_overlap) and still_same_meaning(
            gloss_b, lca_gloss, max_overlap
        ):
            funnel.bump("same_meaning")
            continue
        if still_same_meaning(gloss_a, gloss_b, max_overlap):
            funnel.bump("same_meaning")
            continue

        n_nodes = len(node_list)
        high_overlap = (
            still_same_meaning(gloss_a, lca_gloss, max_overlap)
            or still_same_meaning(gloss_b, lca_gloss, max_overlap)
            or gloss_overlap(gloss_a, gloss_b) >= max_overlap
        )

        key = tuple(sorted([leaf_a_id, leaf_b_id]) + [chosen])
        if key in seen_pairs:
            funnel.bump("duplicate_pair")
            continue
        seen_pairs.add(key)

        edges: list[GraphEdge] = []
        for path in (path_a, path_b):
            for src, dst in zip(path, path[1:]):
                rel = g.edges[src, dst].get("reltype")
                edge = GraphEdge(source=src, target=dst, reltype=rel)
                if not any(e.source == src and e.target == dst for e in edges):
                    edges.append(edge)

        leaf_a = {"lang": lang_a, "term": term_a, "gloss": gloss_a}
        leaf_b = {"lang": lang_b, "term": term_b, "gloss": gloss_b}
        lca = {"lang": lca_lang, "term": lca_term, "gloss": lca_gloss, "id": chosen}
        score = quality_score(
            lang_a=lang_a,
            lang_b=lang_b,
            n_nodes=n_nodes,
            high_overlap=high_overlap,
            lca_is_modern=lca_lang in leaf_langs,
            min_nodes=min_nodes,
        )
        candidates.append(
            {
                "leaf_a": leaf_a,
                "leaf_b": leaf_b,
                "lca": lca,
                "nodes": node_list,
                "edges": edges,
                "quality_score": score,
                "lang_pair": lang_pair_code(lang_a, lang_b, leaf_langs),
            }
        )
        funnel.bump("candidates")
        if score >= min_quality:
            good_count += 1
            if stop_at is not None and good_count >= stop_at:
                funnel.bump("early_exit")
                if progress:
                    progress(
                        "candidate pairs",
                        f"early exit at {good_count} >= min_quality (pairs={funnel.counts['pairs_considered']})",
                    )
                return candidates

    if progress:
        progress(
            "candidate pairs",
            f"{len(candidates)} candidates from {funnel.counts.get('pairs_considered', 0)} pairs",
        )
    return candidates


def make_choices(
    correct_gloss: str,
    distractor_pool: list[str],
    n_choices: int,
    rng,
) -> tuple[list[dict[str, Any]], str]:
    unique: list[str] = []
    for g in distractor_pool:
        if g == correct_gloss:
            continue
        if g not in unique:
            unique.append(g)
    rng.shuffle(unique)
    picked = unique[: n_choices - 1]
    used_glosses = {correct_gloss, *picked}
    while len(picked) < n_choices - 1:
        placeholder_number = len(picked) + 1
        placeholder = f"(unrelated) sense {placeholder_number}"
        while placeholder in used_glosses:
            placeholder_number += 1
            placeholder = f"(unrelated) sense {placeholder_number}"
        picked.append(placeholder)
        used_glosses.add(placeholder)
    options = [correct_gloss] + picked
    rng.shuffle(options)
    choices = [{"id": f"c{i}", "gloss": gloss} for i, gloss in enumerate(options)]
    correct_id = next(c["id"] for c in choices if c["gloss"] == correct_gloss)
    return choices, correct_id


def to_puzzle(cand: dict[str, Any], choices: list[dict[str, Any]], correct: str, g: nx.DiGraph) -> Puzzle:
    nodes = []
    leaf_ids = {
        node_id(cand["leaf_a"]["lang"], cand["leaf_a"]["term"]),
        node_id(cand["leaf_b"]["lang"], cand["leaf_b"]["term"]),
    }
    for nid in cand["nodes"]:
        data = g.nodes[nid]
        role = "leaf" if nid in leaf_ids else "ancestor"
        gloss = cand["leaf_a"]["gloss"] if nid == node_id(cand["leaf_a"]["lang"], cand["leaf_a"]["term"]) else None
        if nid == node_id(cand["leaf_b"]["lang"], cand["leaf_b"]["term"]):
            gloss = cand["leaf_b"]["gloss"]
        if role == "ancestor":
            gloss = cand["lca"]["gloss"] if nid == cand["lca"]["id"] else gloss
        nodes.append(
            GraphNode(
                id=nid,
                lang=data["lang"],
                term=data["term"],
                gloss=gloss,
                role=role,
            ).to_dict()
        )
    edges = [e.to_dict() for e in cand["edges"]]
    graph = {"nodes": nodes, "edges": edges}
    prompt = {"nodes": nodes, "edges": []}
    pid = puzzle_id(cand["leaf_a"], cand["leaf_b"], cand["lca"], edges)
    return Puzzle(
        id=pid,
        enabled=True,
        leaf_a=cand["leaf_a"],
        leaf_b=cand["leaf_b"],
        prompt_graph=prompt,
        answer_graph=graph,
        choices=choices,
        correct_choice=correct,
        quality_score=cand["quality_score"],
        lang_pair=cand["lang_pair"],
        lca=cand["lca"],
    )


def generate_puzzles(
    *,
    n: int | None = None,
    seed: int | None = None,
    lang_pairs: list[str] | None = None,
    min_quality: int | None = None,
    cfg: dict[str, Any] | None = None,
    verbose: bool = False,
) -> tuple[list[Puzzle], Funnel]:
    import random as random_mod

    cfg = cfg or load_config()
    gen_cfg = cfg["generate"]
    n = gen_cfg["n"] if n is None else n
    seed = gen_cfg["seed"] if seed is None else seed
    min_quality = int(gen_cfg["min_quality"] if min_quality is None else min_quality)
    n_choices = int(gen_cfg["n_choices"])
    rng = random_mod.Random(seed)
    timer = StageTimer(enabled=verbose)

    funnel = Funnel()
    edges = load_derived_edges()
    funnel.bump("derived_edges", len(edges))
    timer.stage("load derived edges", f"{len(edges)} rows")

    glosses = load_gloss_index()
    funnel.bump("gloss_index", len(glosses))
    timer.stage("load gloss index", f"{len(glosses)} entries")

    g = build_graph(edges, set(cfg["ancestor_reltypes"]))
    funnel.bump("graph_nodes", g.number_of_nodes())
    funnel.bump("graph_edges", g.number_of_edges())
    timer.stage("build graph", f"{g.number_of_nodes()} nodes / {g.number_of_edges()} edges")

    # When n > 0, stop once we have enough quality survivors. Oversample a little so
    # post-filters (lang_pair) and quality sort still have headroom.
    extract_limit: int | None = None
    if n and n > 0:
        extract_limit = n * 3 if lang_pairs else n

    candidates = extract_candidates(
        g,
        glosses,
        cfg,
        funnel,
        limit=extract_limit,
        min_quality=min_quality,
        progress=timer.stage if verbose else None,
    )
    if lang_pairs:
        want = {p.lower() for p in lang_pairs}
        before = len(candidates)
        candidates = [c for c in candidates if c["lang_pair"] in want]
        funnel.bump("lang_pair_filtered", before - len(candidates))
    timer.stage("filter lang pairs", f"{len(candidates)} left")

    before_q = len(candidates)
    candidates = [c for c in candidates if c["quality_score"] >= min_quality]
    funnel.bump("below_min_quality", before_q - len(candidates))
    timer.stage("filter quality", f"{len(candidates)} left (min_quality={min_quality})")

    candidates.sort(key=lambda c: (-c["quality_score"], c["lang_pair"], c["leaf_a"]["term"], c["leaf_b"]["term"]))
    if n and n > 0:
        candidates = candidates[:n]
    distractors = [c["lca"]["gloss"] for c in candidates if c["lca"].get("gloss")]

    puzzles: list[Puzzle] = []
    for cand in candidates:
        choices, correct = make_choices(cand["lca"]["gloss"], distractors, n_choices, rng)
        puzzles.append(to_puzzle(cand, choices, correct, g))
        funnel.bump("emitted")
    timer.stage("emit puzzles", f"{len(puzzles)} puzzles")

    funnel.counts["emitted"] = len(puzzles)
    return puzzles, funnel


def write_funnel(funnel: Funnel, extra: dict[str, Any] | None = None) -> Path:
    dest = reports_dir()
    dest.mkdir(parents=True, exist_ok=True)
    payload = {"funnel": funnel.as_dict(), **(extra or {})}
    path = dest / "funnel.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
