from __future__ import annotations

from etl.models import Puzzle
from etl.paths import load_config

MIN_PUZZLE_ID_LENGTH = 16


def _err(errors: list[str], puzzle_id: str, msg: str) -> None:
    errors.append(f"{puzzle_id}: {msg}")


def validate_puzzle(p: Puzzle, errors: list[str], cfg: dict | None = None) -> None:
    generation_config = (cfg or load_config())["generate"]
    expected_choices = int(generation_config["n_choices"])
    min_nodes = int(generation_config["min_nodes"])
    max_nodes = int(generation_config["max_nodes"])
    pid = p.id or "<missing-id>"
    if not p.id or len(p.id) < MIN_PUZZLE_ID_LENGTH:
        _err(errors, pid, "id must be a content hash")
    if not isinstance(p.enabled, bool):
        _err(errors, pid, "enabled must be bool")
    for leaf_name, leaf in (("leaf_a", p.leaf_a), ("leaf_b", p.leaf_b)):
        if not isinstance(leaf, dict) or "lang" not in leaf or "term" not in leaf:
            _err(errors, pid, f"{leaf_name} needs lang and term")
    if not p.lang_pair or "-" not in p.lang_pair:
        _err(errors, pid, "lang_pair must look like en-de")
    if not isinstance(p.choices, list):
        _err(errors, pid, "choices must be a list")
        choice_items = []
    else:
        choice_items = p.choices
    if len(choice_items) != expected_choices:
        _err(errors, pid, f"must have exactly {expected_choices} choices")
    if any(not isinstance(choice, dict) for choice in choice_items):
        _err(errors, pid, "choices must contain objects")
    valid_choices = [choice for choice in choice_items if isinstance(choice, dict)]
    ids = [choice.get("id") for choice in valid_choices]
    glosses = [choice.get("gloss") for choice in valid_choices]
    if len(set(ids)) != expected_choices:
        _err(errors, pid, "choice ids must be unique")
    if any(not g for g in glosses):
        _err(errors, pid, "choices need gloss text")
    if p.correct_choice not in ids:
        _err(errors, pid, "correct_choice must match a choice id")
    correct_gloss = next(
        (choice.get("gloss") for choice in valid_choices if choice.get("id") == p.correct_choice),
        None,
    )
    if correct_gloss and any(
        choice.get("id") != p.correct_choice and choice.get("gloss") == correct_gloss
        for choice in valid_choices
    ):
        _err(errors, pid, "distractors must differ from the correct gloss")

    answer = p.answer_graph or {}
    anodes = answer.get("nodes") or []
    aedges = answer.get("edges") or []
    if not (min_nodes <= len(anodes) <= max_nodes):
        _err(errors, pid, f"answer graph must have {min_nodes}-{max_nodes} nodes, got {len(anodes)}")
    node_ids = {n.get("id") for n in anodes if isinstance(n, dict)}
    # prompt_graph is derived at serve/emit time (same nodes, empty edges).

    leaf_ids = {
        f"{p.leaf_a.get('lang')}:{p.leaf_a.get('term')}",
        f"{p.leaf_b.get('lang')}:{p.leaf_b.get('term')}",
    }
    if not leaf_ids <= node_ids:
        _err(errors, pid, "leaves must appear in the graph")
    roles = {n.get("id"): n.get("role") for n in anodes if isinstance(n, dict)}
    for lid in leaf_ids:
        if roles.get(lid) != "leaf":
            _err(errors, pid, f"{lid} should have role=leaf")

    for e in aedges:
        if not isinstance(e, dict) or "from" not in e or "to" not in e:
            _err(errors, pid, "edge must have from/to")
            continue
        if e["from"] not in node_ids or e["to"] not in node_ids:
            _err(errors, pid, "gold edges must use graph node ids")


def validate_puzzles(puzzles: list[Puzzle], cfg: dict | None = None) -> list[str]:
    errors: list[str] = []
    ids: list[str] = []
    cfg = cfg or load_config()
    for p in puzzles:
        ids.append(p.id)
        validate_puzzle(p, errors, cfg)
    if len(ids) != len(set(ids)):
        errors.append("duplicate puzzle ids in set")
    return errors
