from __future__ import annotations

import logging
import unicodedata
from collections import defaultdict, deque
from typing import Any, Callable

import networkx as nx

from etl.core.models import GraphEdge, node_id
from etl.pipeline.gloss import (
    LATIN_FAMILY_LANGS,
    canonical_lemma,
    fold_macrons,
    gloss_for,
    is_grammatical_gloss,
    is_redirect_gloss,
)
from etl.pipeline.quality import assess_pair, term_too_short

log = logging.getLogger(__name__)

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

def normalize_gold_subgraph(
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


def reject_leaf(lang: str, term: str, glosses: dict[str, str]) -> tuple[str | None, str | None]:
    """Return ``(funnel_reason, gloss)``; reason is set when the leaf is unusable."""
    if is_proper_noun_leaf(lang, term):
        return "proper_noun_leaf", None
    if term_too_short(term):
        return "term_too_short", None
    gloss = gloss_for(glosses, lang, term)
    if not gloss:
        return "no_gloss_leaf", None
    return None, gloss


def gold_subgraph_for_pair(
    g: nx.DiGraph,
    glosses: dict[str, str],
    lemmas: dict[str, str],
    *,
    leaf_a_id: str,
    leaf_b_id: str,
    paths_a: dict[str, list[str]],
    paths_b: dict[str, list[str]],
    max_nodes: int,
) -> tuple[str | None, list[str], list[GraphEdge], str | None]:
    """Pick LCA, rewrite form-only LCA, normalize once. Returns reject reason or gold.

    Returns ``(reject_reason, node_list, edges, chosen)``. On success reject is None.
    """
    common = (set(paths_a) & set(paths_b)) - {leaf_a_id, leaf_b_id}
    if not common:
        return "no_lca", [], [], None

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
        return "too_big", [], [], None

    lca_lang = g.nodes[chosen]["lang"]
    lca_term = g.nodes[chosen]["term"]
    lemma_term = canonical_lemma(lemmas, lca_lang, lca_term)
    if lemma_term != lca_term:
        chosen, path_a, path_b, node_list = _rewrite_form_lca(
            g, chosen, lemma_term, path_a, path_b, node_list
        )
    # Single normalize: prefer-latin + unify (covers form-rewrite and Latin-chain cases).
    path_a, path_b, node_list, edges, chosen = normalize_gold_subgraph(
        g,
        glosses,
        path_a,
        path_b,
        chosen=chosen,
        leaf_ids=leaf_ids,
        prefer_latin=True,
    )
    if len(node_list) > max_nodes:
        return "too_big", [], [], None
    return None, node_list, edges, chosen


def reject_candidate(
    g: nx.DiGraph,
    glosses: dict[str, str],
    *,
    leaf_a_id: str,
    leaf_b_id: str,
    lang_a: str,
    lang_b: str,
    term_a: str,
    gloss_a: str,
    term_b: str,
    gloss_b: str,
    node_list: list[str],
    chosen: str,
    min_quality: int,
    seen_pairs: set[tuple[str, str, str]],
) -> tuple[str | None, dict[str, Any] | None, int]:
    """Hard-filter + ancestor scan + dedup. Returns ``(reject, partial_lca, quality)``."""
    leaf_ids = {leaf_a_id, leaf_b_id}
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
        min_quality=min_quality,
    )
    if assessment.reject:
        return assessment.reject, None, 0

    for nid in node_list:
        if nid in leaf_ids:
            continue
        lang = g.nodes[nid]["lang"]
        term = g.nodes[nid]["term"]
        if lang in _MODERN_LEAF_LANGS:
            return "modern_lang_ancestor", None, 0
        gloss = gloss_for(glosses, lang, term) if nid != chosen else lca_gloss
        if gloss and (is_grammatical_gloss(gloss) or is_redirect_gloss(gloss)):
            return "nonlexical_ancestor", None, 0

    key = tuple(sorted([leaf_a_id, leaf_b_id]) + [chosen])
    if key in seen_pairs:
        return "duplicate_pair", None, 0
    seen_pairs.add(key)

    lca = {"lang": lca_lang, "term": lca_term, "gloss": lca_gloss, "id": chosen}
    return None, lca, assessment.quality


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
    funnel: Any,
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
        reason, gloss = reject_leaf(lang, term, glosses)
        if reason:
            funnel.bump(reason)
            continue
        assert gloss is not None
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

        reject, node_list, edges, chosen = gold_subgraph_for_pair(
            g,
            glosses,
            lemmas,
            leaf_a_id=leaf_a_id,
            leaf_b_id=leaf_b_id,
            paths_a=paths_by_leaf[leaf_a_id],
            paths_b=paths_by_leaf[leaf_b_id],
            max_nodes=max_nodes,
        )
        if reject:
            funnel.bump(reject)
            continue
        assert chosen is not None

        reject, lca, score = reject_candidate(
            g,
            glosses,
            leaf_a_id=leaf_a_id,
            leaf_b_id=leaf_b_id,
            lang_a=lang_a,
            lang_b=lang_b,
            term_a=term_a,
            gloss_a=gloss_a,
            term_b=term_b,
            gloss_b=gloss_b,
            node_list=node_list,
            chosen=chosen,
            min_quality=min_quality,
            seen_pairs=seen_pairs,
        )
        if reject:
            funnel.bump(reject)
            continue
        assert lca is not None

        cand = {
            "leaf_a": {"lang": lang_a, "term": term_a, "gloss": gloss_a},
            "leaf_b": {"lang": lang_b, "term": term_b, "gloss": gloss_b},
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
