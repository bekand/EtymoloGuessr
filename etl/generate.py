from __future__ import annotations

import json
import logging
import sys
import time
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Callable

import networkx as nx

from etl.derive import (
    canonical_lemma,
    gloss_for,
    is_grammatical_gloss,
    load_derived_edges,
    load_gloss_index,
    load_lemma_index,
)
from etl.ids import puzzle_id
from etl.models import GraphEdge, GraphNode, Puzzle, node_id
from etl.paths import load_config, reports_dir

log = logging.getLogger(__name__)

FUNCTION_WORDS = {
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

# Orthographies where an initial capital marks a proper noun (not German, which
# capitalizes all nouns). Applied only to modern leaf languages in this set.
_PROPER_NOUN_CASE_LANGS = frozenset({"English", "Spanish", "Portuguese"})


def is_proper_noun_leaf(lang: str, term: str) -> bool:
    """True when a leaf term looks like a proper noun (initial uppercase letter).

    For English / Spanish / Portuguese, Wiktionary lemmas for common words are
    lowercase, so an initial capital is treated as a proper noun and rejected.
    German is exempt: common nouns are capitalized in that orthography.
    """
    if lang not in _PROPER_NOUN_CASE_LANGS:
        return False
    for ch in term:
        if ch.isalpha():
            return ch.isupper()
    return False


def leaf_reuse_key(lang: str, term: str) -> str:
    """Identity for leaf-reuse dedup within a generate batch (lang + term)."""
    return f"{lang}\t{term}"


def _iter_content_tokens(text: str):
    """Yield alphanumeric tokens, skipping function words and short crumbs."""
    buf: list[str] = []
    for ch in text:
        if ch.isalnum():
            buf.append(ch)
        else:
            if buf:
                w = "".join(buf)
                buf = []
                if w not in FUNCTION_WORDS and len(w) >= MIN_TOKEN_LENGTH:
                    yield w
    if buf:
        w = "".join(buf)
        if w not in FUNCTION_WORDS and len(w) >= MIN_TOKEN_LENGTH:
            yield w


def tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    return set(_iter_content_tokens(text.lower()))


def gloss_overlap(a: str | None, b: str | None) -> float:
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def still_same_meaning(leaf_term: str | None, gloss: str | None) -> bool:
    """True when a content word from the leaf term still appears in the gloss."""
    term_tok = tokenize(leaf_term)
    if not term_tok:
        return False
    return bool(term_tok & tokenize(gloss))


def normalize_label(text: str | None) -> str:
    """Casefold a term or gloss for identity checks; strip a reconstruction *."""
    if not text:
        return ""
    s = text.strip().casefold()
    if s.startswith("*"):
        s = s[1:].lstrip()
    return s


def first_content_word(text: str | None) -> str:
    """First non-function token after normalize_label, or empty."""
    for word in _iter_content_tokens(normalize_label(text)):
        return word
    return ""


def leaf_shares_lca_label(
    leaf_term: str | None,
    leaf_gloss: str | None,
    lca_term: str | None,
    lca_gloss: str | None,
) -> bool:
    """True when a leaf and the LCA share a first content word (term or gloss).

    Catches identical labels and head-word matches like leaf ``dragon`` vs LCA
    gloss ``dragon, monster``.
    """
    leaf_labels = {first_content_word(leaf_term), first_content_word(leaf_gloss)} - {""}
    lca_labels = {first_content_word(lca_term), first_content_word(lca_gloss)} - {""}
    return bool(leaf_labels & lca_labels)


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


def ancestor_paths(g: nx.DiGraph, start: str, ancestor_reltypes: set[str]) -> dict[str, list[str]]:
    paths: dict[str, list[str]] = {start: [start]}
    q: deque[str] = deque([start])
    while q:
        node = q.popleft()
        for _, succ, data in g.out_edges(node, data=True):
            if data.get("reltype") not in ancestor_reltypes:
                continue
            if succ not in paths:
                paths[succ] = paths[node] + [succ]
                q.append(succ)
    return paths


def subgraph_from_paths(path_a: list[str], path_b: list[str]) -> list[str]:
    seen: list[str] = []
    for n in path_a + path_b:
        if n not in seen:
            seen.append(n)
    return seen


def _rewrite_form_lca(
    g: nx.DiGraph,
    chosen: str,
    lemma_term: str,
    path_a: list[str],
    path_b: list[str],
    node_list: list[str],
) -> tuple[str, list[str], list[str], list[str]]:
    """Swap a form-only LCA node for its citation lemma. Mutates ``g`` by adding the lemma node/edges."""
    data = g.nodes[chosen]
    lang = data["lang"]
    new_id = node_id(lang, lemma_term)
    if new_id == chosen:
        return chosen, path_a, path_b, node_list
    if new_id not in g:
        g.add_node(new_id, lang=lang, term=lemma_term)
    else:
        g.nodes[new_id].setdefault("lang", lang)
        g.nodes[new_id].setdefault("term", lemma_term)
    for path in (path_a, path_b):
        for src, dst in zip(path, path[1:]):
            if dst != chosen:
                continue
            rel = g.edges[src, dst].get("reltype") if g.has_edge(src, dst) else None
            if not g.has_edge(src, new_id):
                g.add_edge(src, new_id, reltype=rel)

    def _swap(seq: list[str]) -> list[str]:
        return [new_id if n == chosen else n for n in seq]

    return new_id, _swap(path_a), _swap(path_b), _swap(node_list)


def quality_score(
    *,
    lang_a: str,
    lang_b: str,
    term_a: str,
    term_b: str,
    high_overlap: bool,
    lca_is_modern: bool,
) -> int:
    """Integer 0-5. Same-language pairs are heavily down-ranked (−3)."""
    score = 5
    if lang_a == lang_b:
        score -= 3
    if {lang_a, lang_b} == {"Spanish", "Portuguese"}:
        a, b = normalize_label(term_a), normalize_label(term_b)
        if len(a) >= 3 and len(b) >= 3 and a[:3] == b[:3]:
            score -= 2
    if lca_is_modern:
        score -= 1
    if high_overlap:
        score -= 1
    return max(0, score)


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
    lemmas: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    leaf_langs = cfg["leaf_languages"]
    ancestor_reltypes = set(cfg["ancestor_reltypes"])
    generation_config = cfg["generate"]
    max_nodes = int(generation_config["max_nodes"])
    max_overlap = float(generation_config["max_gloss_overlap"])
    lemmas = lemmas or {}

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
        if is_proper_noun_leaf(lang, term):
            funnel.bump("proper_noun_leaf")
            continue
        gloss = gloss_for(glosses, lang, term)
        if not gloss:
            funnel.bump("no_gloss_leaf")
            continue
        gloss_cache[n] = gloss
        paths_by_leaf[n] = ancestor_paths(g, n, ancestor_reltypes)
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
            if len(nodes) > max_nodes:
                continue
            chosen = lca_node_id
            node_list = nodes
            path_a = paths_a[lca_node_id]
            path_b = paths_b[lca_node_id]
            break
        if chosen is None:
            funnel.bump("too_big")
            continue

        lca_lang = g.nodes[chosen]["lang"]
        lca_term = g.nodes[chosen]["term"]
        lemma_term = canonical_lemma(lemmas, lca_lang, lca_term)
        if lemma_term != lca_term:
            chosen, path_a, path_b, node_list = _rewrite_form_lca(
                g, chosen, lemma_term, path_a, path_b, node_list
            )
            lca_lang = g.nodes[chosen]["lang"]
            lca_term = g.nodes[chosen]["term"]
        if not lca_term or len(lca_term) < 3:
            funnel.bump("lca_term_too_short")
            continue
        lca_gloss = gloss_for(glosses, lca_lang, lca_term)
        if not lca_gloss:
            funnel.bump("no_gloss")
            continue
        if is_grammatical_gloss(lca_gloss):
            funnel.bump("inflection_lca")
            continue

        if leaf_shares_lca_label(term_a, gloss_a, lca_term, lca_gloss) or leaf_shares_lca_label(
            term_b, gloss_b, lca_term, lca_gloss
        ):
            funnel.bump("lca_equals_leaf")
            continue

        if still_same_meaning(term_a, lca_gloss) and still_same_meaning(term_b, lca_gloss):
            funnel.bump("same_meaning")
            continue
        if gloss_overlap(gloss_a, gloss_b) >= max_overlap:
            funnel.bump("same_meaning")
            continue

        high_overlap = still_same_meaning(term_a, lca_gloss) or still_same_meaning(term_b, lca_gloss)

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
            term_a=term_a,
            term_b=term_b,
            high_overlap=high_overlap,
            lca_is_modern=lca_lang in leaf_langs,
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
) -> tuple[list[dict[str, Any]], str] | None:
    """Build MC choices from real distractor glosses, or None if the pool is too thin.

    Does not invent placeholder senses. Callers must reject the candidate when
    this returns None (funnel: insufficient_distractors).
    """
    need = n_choices - 1
    unique: list[str] = []
    for gloss in distractor_pool:
        if gloss == correct_gloss:
            continue
        if gloss not in unique:
            unique.append(gloss)
    if len(unique) < need:
        return None
    rng.shuffle(unique)
    picked = unique[:need]
    options = [correct_gloss] + picked
    rng.shuffle(options)
    choices = [{"id": f"c{i}", "gloss": gloss} for i, gloss in enumerate(options)]
    correct_id = next(c["id"] for c in choices if c["gloss"] == correct_gloss)
    return choices, correct_id


def to_puzzle(
    cand: dict[str, Any],
    choices: list[dict[str, Any]],
    correct: str,
    g: nx.DiGraph,
    glosses: dict[str, str],
) -> Puzzle:
    nodes = []
    leaf_ids = {
        node_id(cand["leaf_a"]["lang"], cand["leaf_a"]["term"]),
        node_id(cand["leaf_b"]["lang"], cand["leaf_b"]["term"]),
    }
    for nid in cand["nodes"]:
        data = g.nodes[nid]
        role = "leaf" if nid in leaf_ids else "ancestor"
        nodes.append(
            GraphNode(
                id=nid,
                lang=data["lang"],
                term=data["term"],
                gloss=gloss_for(glosses, data["lang"], data["term"]),
                role=role,
            ).to_dict()
        )
    edges = [e.to_dict() for e in cand["edges"]]
    graph = {"nodes": nodes, "edges": edges}
    pid = puzzle_id(cand["leaf_a"], cand["leaf_b"], cand["lca"], edges)
    return Puzzle(
        id=pid,
        enabled=True,
        leaf_a=cand["leaf_a"],
        leaf_b=cand["leaf_b"],
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

    lemmas = load_lemma_index()
    funnel.bump("lemma_index", len(lemmas))
    timer.stage("load lemma index", f"{len(lemmas)} entries")

    g = build_graph(edges, set(cfg["ancestor_reltypes"]))
    funnel.bump("graph_nodes", g.number_of_nodes())
    funnel.bump("graph_edges", g.number_of_edges())
    timer.stage("build graph", f"{g.number_of_nodes()} nodes / {g.number_of_edges()} edges")

    # When n > 0, stop once we have enough quality survivors. Oversample so
    # lang_pair / leaf-reuse / distractor filters still have headroom, and so the
    # distractor pool (built from all extracted LCA glosses) stays diverse.
    extract_limit: int | None = None
    if n and n > 0:
        # Need ≥ n_choices distinct LCA glosses in the pool; oversample for dedup.
        extract_limit = max(n * 5, n_choices * 4) if lang_pairs else max(n * 4, n_choices * 4)

    candidates = extract_candidates(
        g,
        glosses,
        cfg,
        funnel,
        limit=extract_limit,
        min_quality=min_quality,
        progress=timer.stage if verbose else None,
        lemmas=lemmas,
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

    # Build distractors from the full quality-passing candidate set *before* leaf
    # reuse / emit slicing. Slicing first (as in an earlier revision) left `--n`
    # small batches with too few unique LCA glosses and forced placeholders.
    distractor_pool = [c["lca"]["gloss"] for c in candidates if c["lca"].get("gloss")]

    puzzles: list[Puzzle] = []
    used_leaves: set[str] = set()
    for cand in candidates:
        if n and n > 0 and len(puzzles) >= n:
            break
        key_a = leaf_reuse_key(cand["leaf_a"]["lang"], cand["leaf_a"]["term"])
        key_b = leaf_reuse_key(cand["leaf_b"]["lang"], cand["leaf_b"]["term"])
        if key_a in used_leaves or key_b in used_leaves:
            funnel.bump("leaf_reuse")
            continue
        built = make_choices(cand["lca"]["gloss"], distractor_pool, n_choices, rng)
        if built is None:
            funnel.bump("insufficient_distractors")
            continue
        choices, correct = built
        puzzles.append(to_puzzle(cand, choices, correct, g, glosses))
        used_leaves.add(key_a)
        used_leaves.add(key_b)
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
