from __future__ import annotations

from collections import defaultdict
from typing import Any

import networkx as nx

from etl.core.ids import puzzle_id
from etl.core.models import GraphNode, Puzzle, node_id
from etl.pipeline.extract import involves_english
from etl.pipeline.gloss import gloss_for, is_grammatical_gloss, is_redirect_gloss


def leaf_reuse_key(lang: str, term: str) -> str:
    """Identity for leaf-reuse dedup within a generate batch (lang + term)."""
    return f"{lang}\t{term}"


def make_choices(
    correct_gloss: str,
    distractor_pool: list[str],
    n_choices: int,
    rng,
) -> tuple[list[dict[str, Any]], str] | None:
    """Build MC choices from real distractor glosses, or None if the pool is too thin.

    ``distractor_pool`` should already be unique lexical glosses (callers pre-filter
    redirects / grammatical stubs once). Does not invent placeholder senses.
    """
    need = n_choices - 1
    others = [gloss for gloss in distractor_pool if gloss != correct_gloss]
    if len(others) < need:
        return None
    picked = rng.sample(others, need)
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



def build_distractor_pool(candidates: list[dict[str, Any]]) -> list[str]:
    """Unique lexical LCA glosses from quality-passing candidates."""
    distractor_pool: list[str] = []
    seen_glosses: set[str] = set()
    for cand in candidates:
        gloss = cand["lca"].get("gloss")
        if not gloss or gloss in seen_glosses:
            continue
        if is_redirect_gloss(gloss) or is_grammatical_gloss(gloss):
            continue
        seen_glosses.add(gloss)
        distractor_pool.append(gloss)
    return distractor_pool


def emit_puzzles(
    candidates: list[dict[str, Any]],
    *,
    g: nx.DiGraph,
    glosses: dict[str, str],
    funnel,
    rng,
    n: int,
    n_choices: int,
) -> list[Puzzle]:
    """Water-fill emit: quality buckets, English/other balance, leaf reuse, MC choices."""
    distractor_pool = build_distractor_pool(candidates)
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

    return puzzles
