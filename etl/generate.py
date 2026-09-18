from __future__ import annotations

import json
import logging
import sys
import time
import unicodedata
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Callable

import networkx as nx

from etl.derive import (
    LATIN_FAMILY_LANGS,
    canonical_lemma,
    fold_macrons,
    gloss_for,
    is_redirect_gloss,
    is_grammatical_gloss,
    load_derived_edges,
    load_gloss_index,
    load_lemma_index,
)
from etl.ids import puzzle_id
from etl.models import GraphEdge, GraphNode, Puzzle, node_id
from etl.paths import load_config, reports_dir
from etl.quality import assess_pair, term_too_short

log = logging.getLogger(__name__)

# Orthographies where an initial capital marks a proper noun (not German, which
# capitalizes all nouns). Applied only to modern leaf languages in this set.
_PROPER_NOUN_CASE_LANGS = frozenset({"English", "Spanish", "Portuguese"})

# Modern languages that may be puzzle leaves but must not appear as gold-graph
# intermediates (loan hops like Spanish→English→Latin).
_MODERN_LEAF_LANGS = frozenset({"English", "Spanish", "Portuguese", "German"})


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


def lang_pair_code(lang_a: str, lang_b: str, leaf_codes: dict[str, str]) -> str:
    ca, cb = leaf_codes[lang_a], leaf_codes[lang_b]
    return "-".join(sorted([ca, cb]))


def involves_english(cand: dict[str, Any]) -> bool:
    """True when either leaf is English (English-involving pair)."""
    return cand["leaf_a"]["lang"] == "English" or cand["leaf_b"]["lang"] == "English"


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


def _edges_from_paths(g: nx.DiGraph, path_a: list[str], path_b: list[str]) -> list[GraphEdge]:
    edges: list[GraphEdge] = []
    for path in (path_a, path_b):
        for src, dst in zip(path, path[1:]):
            rel = g.edges[src, dst].get("reltype")
            edge = GraphEdge(source=src, target=dst, reltype=rel)
            if not any(e.source == src and e.target == dst for e in edges):
                edges.append(edge)
    return edges


def _latin_family_neighbors(g: nx.DiGraph, leaf_id: str) -> list[str]:
    """Direct Latin-family out-neighbors of ``leaf_id``, sorted for stability."""
    out: list[str] = []
    for _, succ in g.out_edges(leaf_id):
        if g.nodes[succ].get("lang") in LATIN_FAMILY_LANGS:
            out.append(succ)
    out.sort()
    return out


def prefer_latin_chain_path(
    g: nx.DiGraph,
    path: list[str],
    lca_id: str,
) -> list[str]:
    """Rewrite leaf→LCA into leaf→Latin→LCA when a parallel Latin hop exists.

    etymology-db often encodes ``from Late Latin X, from Greek Y`` as two edges
    from the modern leaf. BFS then picks the direct Greek hop. Prefer routing
    through a Latin-family sibling and add ``Latin → LCA`` when missing.

    Skip when the LCA is already Latin-family (form-lemma rewrites, Latin LCAs).
    """
    if len(path) != 2 or path[0] == lca_id or path[-1] != lca_id:
        return path
    if g.nodes[lca_id].get("lang") in LATIN_FAMILY_LANGS:
        return path
    leaf_id = path[0]
    latin_neighbors = _latin_family_neighbors(g, leaf_id)
    if not latin_neighbors:
        return path
    # Prefer a Latin node that already points at the LCA; else first sorted.
    chosen_latin = None
    for nid in latin_neighbors:
        if g.has_edge(nid, lca_id):
            chosen_latin = nid
            break
    if chosen_latin is None:
        chosen_latin = latin_neighbors[0]
    if not g.has_edge(chosen_latin, lca_id):
        # Reconstruct the usual Wiktionary chain without inventing a new etymon.
        leaf_rel = g.edges[leaf_id, lca_id].get("reltype") if g.has_edge(leaf_id, lca_id) else "derived_from"
        g.add_edge(chosen_latin, lca_id, reltype=leaf_rel)
    return [leaf_id, chosen_latin, lca_id]


def _term_has_combining_marks(term: str) -> bool:
    decomposed = unicodedata.normalize("NFD", term)
    return any(unicodedata.category(ch) == "Mn" for ch in decomposed)


def _ancestors_equivalent(
    lang_a: str,
    term_a: str,
    gloss_a: str,
    lang_b: str,
    term_b: str,
    gloss_b: str,
) -> bool:
    """True when two ancestors should collapse (same gloss + same-lang or Latin-family twin)."""
    if gloss_a != gloss_b:
        return False
    if lang_a == lang_b:
        return True
    if lang_a in LATIN_FAMILY_LANGS and lang_b in LATIN_FAMILY_LANGS:
        return fold_macrons(term_a).casefold() == fold_macrons(term_b).casefold()
    return False


def _pick_unify_survivor(members: list[str], *, g: nx.DiGraph, lca_id: str) -> str:
    """Choose which node id survives a same-gloss merge group."""

    def rank(nid: str) -> tuple:
        data = g.nodes[nid]
        lang = data.get("lang") or ""
        term = data.get("term") or ""
        return (
            0 if nid == lca_id else 1,
            0 if lang == "Latin" else 1,
            0 if _term_has_combining_marks(term) else 1,
            nid,
        )

    return min(members, key=rank)


def unify_same_gloss_ancestors(
    node_ids: list[str],
    edges: list[GraphEdge],
    *,
    g: nx.DiGraph,
    glosses: dict[str, str],
    leaf_ids: set[str],
    lca_id: str,
) -> tuple[list[str], list[GraphEdge], str]:
    """Collapse ancestor duplicates that share a gloss.

    Merges (1) same-language nodes with the same gloss, and (2) Latin-family
    nodes with the same macron-folded spelling and gloss. Prefer LCA, then
    Classical Latin, then diacritic forms.
    """
    ancestors: list[str] = []
    gloss_by_id: dict[str, str] = {}
    for nid in node_ids:
        if nid in leaf_ids:
            continue
        data = g.nodes[nid]
        gloss = gloss_for(glosses, data["lang"], data["term"])
        if not gloss or not str(gloss).strip():
            continue
        gloss_by_id[nid] = str(gloss).strip()
        ancestors.append(nid)

    if len(ancestors) < 2:
        return node_ids, edges, lca_id

    parent = {nid: nid for nid in ancestors}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, a in enumerate(ancestors):
        da = g.nodes[a]
        for b in ancestors[i + 1 :]:
            db = g.nodes[b]
            if _ancestors_equivalent(
                da["lang"],
                da["term"],
                gloss_by_id[a],
                db["lang"],
                db["term"],
                gloss_by_id[b],
            ):
                union(a, b)

    groups: dict[str, list[str]] = defaultdict(list)
    for nid in ancestors:
        groups[find(nid)].append(nid)

    remap: dict[str, str] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        survivor = _pick_unify_survivor(members, g=g, lca_id=lca_id)
        for nid in members:
            if nid != survivor:
                remap[nid] = survivor

    if not remap:
        return node_ids, edges, lca_id

    def map_id(nid: str) -> str:
        return remap.get(nid, nid)

    new_lca = map_id(lca_id)
    new_nodes: list[str] = []
    seen: set[str] = set()
    for nid in node_ids:
        mid = map_id(nid)
        if mid not in seen:
            seen.add(mid)
            new_nodes.append(mid)

    new_edges: list[GraphEdge] = []
    edge_seen: set[tuple[str, str, str | None]] = set()
    for edge in edges:
        src, dst = map_id(edge.source), map_id(edge.target)
        if src == dst:
            continue
        key = (src, dst, edge.reltype)
        if key in edge_seen:
            continue
        edge_seen.add(key)
        new_edges.append(GraphEdge(source=src, target=dst, reltype=edge.reltype))

    return new_nodes, new_edges, new_lca


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


def _rebuild_candidate_paths(
    g: nx.DiGraph,
    glosses: dict[str, str],
    path_a: list[str],
    path_b: list[str],
    *,
    chosen: str,
    leaf_ids: set[str],
    prefer_latin: bool = False,
) -> tuple[list[str], list[str], list[str], list[GraphEdge], str]:
    """Rebuild and unify a candidate graph after its LCA or paths change."""
    if prefer_latin:
        path_a = prefer_latin_chain_path(g, path_a, chosen)
        path_b = prefer_latin_chain_path(g, path_b, chosen)
    node_list = subgraph_from_paths(path_a, path_b)
    edges = _edges_from_paths(g, path_a, path_b)
    node_list, edges, chosen = unify_same_gloss_ancestors(
        node_list,
        edges,
        g=g,
        glosses=glosses,
        leaf_ids=leaf_ids,
        lca_id=chosen,
    )
    return path_a, path_b, node_list, edges, chosen


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
    rng=None,
) -> Any:
    """Yield each unordered leaf pair that shares at least one ancestor (once).

    Avoids the naive all-pairs O(L^2) walk when most leaves do not share ancestry.
    Worst case (one universal ancestor) is still O(L^2), but typical etymology
    graphs are much sparser.

    Ancestors stay ordered by descending fan-out (speed). When ``rng`` is set,
    one pair is taken from each ancestor per round (round-robin) so English-only
    families cannot monopolize early extraction before non-English ones appear.
    """
    by_ancestor: dict[str, list[str]] = defaultdict(list)
    for leaf_id in leaves_with_gloss:
        for anc in paths_by_leaf[leaf_id]:
            if anc != leaf_id:
                by_ancestor[anc].append(leaf_id)

    fanout_groups: dict[int, list[str]] = defaultdict(list)
    for anc, members in by_ancestor.items():
        fanout_groups[len(members)].append(anc)
    ancestor_order: list[str] = []
    for fan in sorted(fanout_groups.keys(), reverse=True):
        chunk = fanout_groups[fan]
        chunk.sort()
        if rng is not None:
            rng.shuffle(chunk)
        ancestor_order.extend(chunk)

    seen_pairs: set[tuple[str, str]] = set()

    if rng is None:
        for anc in ancestor_order:
            group = sorted(set(by_ancestor[anc]))
            for i, leaf_a_id in enumerate(group):
                for leaf_b_id in group[i + 1 :]:
                    key = (leaf_a_id, leaf_b_id) if leaf_a_id < leaf_b_id else (leaf_b_id, leaf_a_id)
                    if key in seen_pairs:
                        continue
                    seen_pairs.add(key)
                    yield leaf_a_id, leaf_b_id
        return

    # Cursor per ancestor: (shuffled group, i, j). Round-robin one pair each.
    # Sort before shuffle so a seeded rng is independent of PYTHONHASHSEED
    # (list(set(...)) order is randomized per process).
    cursors: list[list[Any]] = []
    for anc in ancestor_order:
        group = sorted(set(by_ancestor[anc]))
        if len(group) < 2:
            continue
        rng.shuffle(group)
        cursors.append([group, 0, 1])

    while cursors:
        rng.shuffle(cursors)
        alive: list[list[Any]] = []
        for cur in cursors:
            group, i, j = cur
            emitted = False
            while i < len(group) - 1:
                while j < len(group):
                    leaf_a_id, leaf_b_id = group[i], group[j]
                    j += 1
                    key = (
                        (leaf_a_id, leaf_b_id)
                        if leaf_a_id < leaf_b_id
                        else (leaf_b_id, leaf_a_id)
                    )
                    if key in seen_pairs:
                        continue
                    seen_pairs.add(key)
                    cur[1], cur[2] = i, j
                    yield leaf_a_id, leaf_b_id
                    emitted = True
                    break
                if emitted:
                    break
                i += 1
                j = i + 1
                cur[1], cur[2] = i, j
            if i < len(group) - 1:
                alive.append(cur)
        cursors = alive


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
    rng=None,
) -> list[dict[str, Any]]:
    leaf_langs = cfg["leaf_languages"]
    ancestor_reltypes = set(cfg["ancestor_reltypes"])
    generation_config = cfg["generate"]
    max_nodes = int(generation_config["max_nodes"])
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
        if term_too_short(term):
            funnel.bump("term_too_short")
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
    good_en = 0
    good_other = 0
    # Per-bucket headroom: stop when both English and non-English quality counts
    # reach need_each, or total hits hard_cap (one-bucket graphs / --lang-pair).
    stop_at = None if not limit or limit <= 0 else limit
    need_each = None if stop_at is None else max(1, stop_at // 2)
    hard_cap = None if stop_at is None else stop_at * 2

    for leaf_a_id, leaf_b_id in _iter_related_leaf_pairs(leaves_with_gloss, paths_by_leaf, rng=rng):
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
        edges: list[GraphEdge] = []
        leaf_ids = {leaf_a_id, leaf_b_id}
        for lca_node_id in ranked:
            trial_a = paths_a[lca_node_id]
            trial_b = paths_b[lca_node_id]
            trial_nodes = subgraph_from_paths(trial_a, trial_b)
            trial_edges = _edges_from_paths(g, trial_a, trial_b)
            trial_nodes, trial_edges, trial_lca = unify_same_gloss_ancestors(
                trial_nodes,
                trial_edges,
                g=g,
                glosses=glosses,
                leaf_ids=leaf_ids,
                lca_id=lca_node_id,
            )
            if len(trial_nodes) > max_nodes:
                continue
            chosen = trial_lca
            node_list = trial_nodes
            path_a = trial_a
            path_b = trial_b
            edges = trial_edges
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
            path_a, path_b, node_list, edges, chosen = _rebuild_candidate_paths(
                g,
                glosses,
                path_a,
                path_b,
                chosen=chosen,
                leaf_ids=leaf_ids,
            )
        path_a, path_b, node_list, edges, chosen = _rebuild_candidate_paths(
            g,
            glosses,
            path_a,
            path_b,
            chosen=chosen,
            leaf_ids=leaf_ids,
            prefer_latin=True,
        )
        if len(node_list) > max_nodes:
            funnel.bump("too_big")
            continue
        lca_lang = g.nodes[chosen]["lang"]
        lca_term = g.nodes[chosen]["term"]
        lca_gloss = gloss_for(glosses, lca_lang, lca_term)
        assessment = assess_pair(
            lang_a=lang_a,
            lang_b=lang_b,
            term_a=term_a,
            gloss_a=gloss_a,
            term_b=term_b,
            gloss_b=gloss_b,
            lca_term=lca_term,
            lca_gloss=lca_gloss,
        )
        if assessment.reject:
            funnel.bump(assessment.reject)
            continue

        modern_ancestor = False
        nonlexical = False
        for nid in node_list:
            if nid in leaf_ids:
                continue
            lang = g.nodes[nid]["lang"]
            term = g.nodes[nid]["term"]
            if lang in _MODERN_LEAF_LANGS:
                modern_ancestor = True
                break
            gloss = gloss_for(glosses, lang, term) if nid != chosen else lca_gloss
            if gloss and (is_grammatical_gloss(gloss) or is_redirect_gloss(gloss)):
                nonlexical = True
                break
        if modern_ancestor:
            funnel.bump("modern_lang_ancestor")
            continue
        if nonlexical:
            funnel.bump("nonlexical_ancestor")
            continue

        key = tuple(sorted([leaf_a_id, leaf_b_id]) + [chosen])
        if key in seen_pairs:
            funnel.bump("duplicate_pair")
            continue
        seen_pairs.add(key)

        leaf_a = {"lang": lang_a, "term": term_a, "gloss": gloss_a}
        leaf_b = {"lang": lang_b, "term": term_b, "gloss": gloss_b}
        lca = {"lang": lca_lang, "term": lca_term, "gloss": lca_gloss, "id": chosen}
        score = assessment.quality
        cand = {
            "leaf_a": leaf_a,
            "leaf_b": leaf_b,
            "lca": lca,
            "nodes": node_list,
            "edges": edges,
            "quality_score": score,
            "lang_pair": lang_pair_code(lang_a, lang_b, leaf_langs),
        }
        candidates.append(cand)
        funnel.bump("candidates")
        if score >= min_quality and need_each is not None and hard_cap is not None:
            if involves_english(cand):
                good_en += 1
            else:
                good_other += 1
            both_full = good_en >= need_each and good_other >= need_each
            # One-bucket graphs never fill the empty side; stop once the leading
            # side alone hits hard_cap (round-robin makes mixed graphs fill both).
            starved = min(good_en, good_other) == 0 and max(good_en, good_other) >= hard_cap
            if both_full or starved:
                funnel.bump("early_exit")
                if progress:
                    progress(
                        "candidate pairs",
                        f"early exit en={good_en} other={good_other} "
                        f"(pairs={funnel.counts['pairs_considered']})",
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
        if is_redirect_gloss(gloss) or is_grammatical_gloss(gloss):
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


def prepare_score_buckets(
    candidates: list[dict[str, Any]],
    rng,
) -> list[tuple[list[dict[str, Any]], list[dict[str, Any]]]]:
    """Group quality-passing candidates by score (desc), shuffle English / other."""
    by_score: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for cand in candidates:
        by_score[cand["quality_score"]].append(cand)
    buckets: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]] = []
    for score in sorted(by_score.keys(), reverse=True):
        en_bucket = [c for c in by_score[score] if involves_english(c)]
        other_bucket = [c for c in by_score[score] if not involves_english(c)]
        rng.shuffle(en_bucket)
        rng.shuffle(other_bucket)
        buckets.append((en_bucket, other_bucket))
    return buckets


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
        rng=rng,
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

    # Build distractors from the full quality-passing candidate set *before* leaf
    # reuse / emit slicing. Slicing first (as in an earlier revision) left `--n`
    # small batches with too few unique LCA glosses and forced placeholders.
    distractor_pool = [c["lca"]["gloss"] for c in candidates if c["lca"].get("gloss")]

    # Quality-first, then English vs non-English water-fill with seeded shuffles
    # so A-words and de-en do not lock shared leaves before other pairs.
    puzzles: list[Puzzle] = []
    used_leaves: set[str] = set()

    def _try_emit(cand: dict[str, Any]) -> bool:
        key_a = leaf_reuse_key(cand["leaf_a"]["lang"], cand["leaf_a"]["term"])
        key_b = leaf_reuse_key(cand["leaf_b"]["lang"], cand["leaf_b"]["term"])
        if key_a in used_leaves or key_b in used_leaves:
            funnel.bump("leaf_reuse")
            return False
        built = make_choices(cand["lca"]["gloss"], distractor_pool, n_choices, rng)
        if built is None:
            funnel.bump("insufficient_distractors")
            return False
        choices, correct = built
        puzzles.append(to_puzzle(cand, choices, correct, g, glosses))
        used_leaves.add(key_a)
        used_leaves.add(key_b)
        funnel.bump("emitted")
        return True

    for en_bucket, other_bucket in prepare_score_buckets(candidates, rng):
        buckets = (en_bucket, other_bucket)
        indexes = [0, 0]
        emitted = [0, 0]
        while any(index < len(bucket) for bucket, index in zip(buckets, indexes)):
            if n and n > 0 and len(puzzles) >= n:
                break
            preferred = 0 if emitted[0] <= emitted[1] else 1
            order = (preferred, 1 - preferred)
            bucket_index = next(
                (index for index in order if indexes[index] < len(buckets[index])),
                None,
            )
            if bucket_index is None:
                break
            candidate = buckets[bucket_index][indexes[bucket_index]]
            indexes[bucket_index] += 1
            if _try_emit(candidate):
                emitted[bucket_index] += 1
        if n and n > 0 and len(puzzles) >= n:
            break

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
