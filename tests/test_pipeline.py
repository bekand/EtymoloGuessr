from typing import Any, cast

import pandas as pd
import pytest

from etl.derive import is_junk_term
from etl.generate import (
    Funnel,
    build_graph,
    extract_candidates,
    gloss_overlap,
    is_proper_noun_leaf,
    leaf_reuse_key,
    make_choices,
    quality_score,
    still_same_meaning,
)
from etl.ids import puzzle_id
from etl.validate import validate_puzzles
from etl.models import Puzzle


def test_junk_terms():
    assert is_junk_term(None)
    assert is_junk_term("-ness")
    assert is_junk_term("junk compound")
    assert not is_junk_term("*giftiz")
    assert not is_junk_term("gift")


def test_proper_noun_leaf_filter():
    assert is_proper_noun_leaf("English", "Paris")
    assert is_proper_noun_leaf("Spanish", "Madrid")
    assert is_proper_noun_leaf("Portuguese", "Lisboa")
    assert not is_proper_noun_leaf("English", "gift")
    assert not is_proper_noun_leaf("English", "patio")
    # German capitalizes common nouns — not treated as proper nouns here.
    assert not is_proper_noun_leaf("German", "Gift")
    assert not is_proper_noun_leaf("German", "Hund")
    assert leaf_reuse_key("English", "gift") == "English\tgift"


def test_gloss_overlap_detects_same_meaning():
    assert gloss_overlap("a dog used for hunting", "a dog") > 0.2
    assert gloss_overlap("a present given to someone", "poison; a toxic substance") < 0.2
    assert still_same_meaning("a dog used for hunting", "a dog", 0.5)
    assert still_same_meaning("a dog", "a dog", 0.5)
    assert not still_same_meaning("a present given to someone", "poison; a toxic substance", 0.5)


def test_puzzle_id_order_invariant():
    a = {"lang": "English", "term": "gift"}
    b = {"lang": "German", "term": "Gift"}
    lca = {"lang": "Proto-Germanic", "term": "*giftiz"}
    e1 = [{"from": "English:gift", "to": "Proto-Germanic:*giftiz"}]
    e2 = [{"from": "German:Gift", "to": "Proto-Germanic:*giftiz"}]
    assert puzzle_id(a, b, lca, e1 + e2) == puzzle_id(b, a, lca, list(reversed(e1 + e2)))


def test_quality_score_is_integer_rubric():
    base: dict[str, Any] = dict(n_nodes=4, high_overlap=False, lca_is_modern=False)
    assert quality_score(lang_a="English", lang_b="German", **base) == 5
    assert quality_score(lang_a="English", lang_b="English", **base) == 2  # −3 same-lang
    assert quality_score(lang_a="Spanish", lang_b="Portuguese", **base) == 4
    assert quality_score(lang_a="English", lang_b="German", **{**base, "lca_is_modern": True}) == 4
    assert quality_score(lang_a="English", lang_b="German", **{**base, "high_overlap": True}) == 4
    assert quality_score(lang_a="English", lang_b="German", **{**base, "n_nodes": 3}) == 4
    worst_cross = quality_score(
        lang_a="Spanish",
        lang_b="Portuguese",
        n_nodes=3,
        high_overlap=True,
        lca_is_modern=True,
    )
    assert worst_cross == 1
    assert isinstance(worst_cross, int)
    assert (
        quality_score(
            lang_a="English",
            lang_b="English",
            n_nodes=3,
            high_overlap=True,
            lca_is_modern=True,
        )
        == 0
    )


def test_make_choices_requires_real_distractors():
    rng = __import__("random").Random(1)
    assert make_choices("ancestor gloss", ["only one other"], n_choices=4, rng=rng) is None
    built = make_choices(
        "ancestor gloss",
        ["sense a", "sense b", "sense c", "ancestor gloss"],
        n_choices=4,
        rng=rng,
    )
    assert built is not None
    choices, correct_id = built
    glosses = [choice["gloss"] for choice in choices]
    assert len(glosses) == 4
    assert len(set(glosses)) == 4
    assert all(not g.startswith("(unrelated)") for g in glosses)
    assert choices[[choice["id"] for choice in choices].index(correct_id)]["gloss"] == "ancestor gloss"


def _synth_shift_graph(n_leaves: int, shared_ancestors: int = 20, *, include_proper: bool = False):
    """Many modern leaves under proto ancestors with distinct glosses (semantic shift)."""
    rows = []
    glosses: dict[str, str] = {}
    for i in range(shared_ancestors):
        glosses[f"Proto-Germanic\t*root{i}"] = f"ancient sense {i} poison venom toxin"
    for i in range(n_leaves):
        leaf_lang = ["English", "German", "Spanish", "Portuguese"][i % 4]
        term = f"Word{i}" if include_proper and leaf_lang == "English" and i % 8 == 0 else f"word{i}"
        anc = f"*root{i % shared_ancestors}"
        rows.append(
            dict(
                term=term,
                lang=leaf_lang,
                reltype="inherited_from",
                related_term=anc,
                related_lang="Proto-Germanic",
            )
        )
        glosses[f"{leaf_lang}\t{term}"] = f"unique leaf gloss {i} zebra{i} quartz{i}"
    df = pd.DataFrame(rows)
    g = build_graph(df, {"inherited_from", "borrowed_from", "derived_from", "root"})
    cfg = {
        "leaf_languages": {"English": "en", "Spanish": "es", "Portuguese": "pt", "German": "de"},
        "ancestor_reltypes": ["inherited_from", "borrowed_from", "derived_from", "root"],
        "generate": {
            "min_nodes": 3,
            "max_nodes": 5,
            "max_ancestor_depth": 6,
            "max_gloss_overlap": 0.5,
            "n": 10,
            "min_quality": 3,
            "n_choices": 4,
            "seed": 1,
        },
    }
    return g, glosses, cfg


def test_extract_candidates_early_exit_respects_limit():
    g, glosses, cfg = _synth_shift_graph(400, shared_ancestors=10)
    funnel = Funnel()
    cands = extract_candidates(g, glosses, cfg, funnel, limit=10, min_quality=3)
    assert len(cands) >= 10
    assert sum(1 for c in cands if c["quality_score"] >= 3) >= 10
    assert funnel.counts.get("early_exit", 0) == 1
    # Without early exit this graph considers tens of thousands of related pairs.
    assert funnel.counts["pairs_considered"] < 5000


def test_extract_candidates_skips_proper_noun_leaves():
    g, glosses, cfg = _synth_shift_graph(40, shared_ancestors=8, include_proper=True)
    funnel = Funnel()
    extract_candidates(g, glosses, cfg, funnel)
    assert funnel.counts.get("proper_noun_leaf", 0) >= 1


def test_extract_candidates_skips_unrelated_leaf_pairs():
    """Leaves under disjoint ancestors must not inflate pairs_considered."""
    rows = [
        dict(term="a1", lang="English", reltype="inherited_from", related_term="*ra", related_lang="Proto-Germanic"),
        dict(term="a2", lang="German", reltype="inherited_from", related_term="*ra", related_lang="Proto-Germanic"),
        dict(term="b1", lang="Spanish", reltype="inherited_from", related_term="*rb", related_lang="Proto-Germanic"),
        dict(term="b2", lang="Portuguese", reltype="inherited_from", related_term="*rb", related_lang="Proto-Germanic"),
    ]
    glosses = {
        "English\ta1": "modern alpha one",
        "German\ta2": "modern alpha two",
        "Spanish\tb1": "modern beta one",
        "Portuguese\tb2": "modern beta two",
        "Proto-Germanic\t*ra": "ancient poison ra",
        "Proto-Germanic\t*rb": "ancient venom rb",
    }
    g = build_graph(pd.DataFrame(rows), {"inherited_from"})
    cfg = {
        "leaf_languages": {"English": "en", "Spanish": "es", "Portuguese": "pt", "German": "de"},
        "ancestor_reltypes": ["inherited_from"],
        "generate": {
            "min_nodes": 3,
            "max_nodes": 5,
            "max_ancestor_depth": 6,
            "max_gloss_overlap": 0.5,
        },
    }
    funnel = Funnel()
    extract_candidates(g, glosses, cfg, funnel)
    # Naive all-pairs would be C(4,2)=6; related-only is 2 (a1-a2 and b1-b2).
    assert funnel.counts["pairs_considered"] == 2


def _two_leaf_lca_cfg() -> dict[str, Any]:
    return {
        "leaf_languages": {"English": "en", "Spanish": "es", "Portuguese": "pt", "German": "de"},
        "ancestor_reltypes": ["inherited_from"],
        "generate": {
            "min_nodes": 3,
            "max_nodes": 5,
            "max_ancestor_depth": 6,
            "max_gloss_overlap": 0.5,
        },
    }


def test_extract_candidates_rejects_short_lca_term():
    """LCA terms shorter than 3 characters are rejected (funnel: lca_term_too_short)."""
    rows = [
        dict(term="leafx", lang="English", reltype="inherited_from", related_term="ab", related_lang="Proto-Germanic"),
        dict(term="leafy", lang="German", reltype="inherited_from", related_term="ab", related_lang="Proto-Germanic"),
    ]
    glosses = {
        "English\tleafx": "modern sense alpha zebra",
        "German\tleafy": "modern sense beta quartz",
        "Proto-Germanic\tab": "ancient short root poison",
    }
    g = build_graph(pd.DataFrame(rows), {"inherited_from"})
    funnel = Funnel()
    cands = extract_candidates(g, glosses, _two_leaf_lca_cfg(), funnel)
    assert cands == []
    assert funnel.counts.get("lca_term_too_short", 0) >= 1
    assert funnel.counts.get("candidates", 0) == 0


def test_extract_candidates_rejects_missing_lca_gloss():
    """Missing LCA gloss is rejected via existing no_gloss funnel reason."""
    rows = [
        dict(term="leafx", lang="English", reltype="inherited_from", related_term="*longroot", related_lang="Proto-Germanic"),
        dict(term="leafy", lang="German", reltype="inherited_from", related_term="*longroot", related_lang="Proto-Germanic"),
    ]
    glosses = {
        "English\tleafx": "modern sense alpha zebra",
        "German\tleafy": "modern sense beta quartz",
        # intentionally no Proto-Germanic:*longroot gloss
    }
    g = build_graph(pd.DataFrame(rows), {"inherited_from"})
    funnel = Funnel()
    cands = extract_candidates(g, glosses, _two_leaf_lca_cfg(), funnel)
    assert cands == []
    assert funnel.counts.get("no_gloss", 0) >= 1
    assert funnel.counts.get("candidates", 0) == 0


def test_extract_candidates_accepts_lca_term_length_three():
    """Boundary: LCA term of exactly 3 characters is allowed when glossed."""
    rows = [
        dict(term="leafx", lang="English", reltype="inherited_from", related_term="abc", related_lang="Proto-Germanic"),
        dict(term="leafy", lang="German", reltype="inherited_from", related_term="abc", related_lang="Proto-Germanic"),
    ]
    glosses = {
        "English\tleafx": "modern sense alpha zebra",
        "German\tleafy": "modern sense beta quartz",
        "Proto-Germanic\tabc": "ancient root poison venom",
    }
    g = build_graph(pd.DataFrame(rows), {"inherited_from"})
    funnel = Funnel()
    cands = extract_candidates(g, glosses, _two_leaf_lca_cfg(), funnel)
    assert len(cands) >= 1
    assert cands[0]["lca"]["term"] == "abc"
    assert funnel.counts.get("lca_term_too_short", 0) == 0
    assert funnel.counts.get("no_gloss", 0) == 0


def test_validate_happy_path():
    p = Puzzle(
        id="a" * 32,
        enabled=True,
        leaf_a={"lang": "English", "term": "gift", "gloss": "present"},
        leaf_b={"lang": "German", "term": "Gift", "gloss": "poison"},
        answer_graph={
            "nodes": [
                {"id": "English:gift", "role": "leaf"},
                {"id": "German:Gift", "role": "leaf"},
                {"id": "Proto-Germanic:*giftiz", "role": "ancestor"},
            ],
            "edges": [
                {"from": "English:gift", "to": "Proto-Germanic:*giftiz"},
                {"from": "German:Gift", "to": "Proto-Germanic:*giftiz"},
            ],
        },
        choices=[
            {"id": "c0", "gloss": "something given"},
            {"id": "c1", "gloss": "a beast"},
            {"id": "c2", "gloss": "to die"},
            {"id": "c3", "gloss": "a servant"},
        ],
        correct_choice="c0",
        quality_score=4,
        lang_pair="de-en",
    )
    assert validate_puzzles([p]) == []
    assert p.prompt_graph["edges"] == []
    assert {n["id"] for n in p.prompt_graph["nodes"]} == {n["id"] for n in p.answer_graph["nodes"]}
    assert "prompt_graph" not in p.to_dict()


def test_validate_reports_malformed_choices_and_graph_together():
    p = Puzzle(
        id="a" * 32,
        enabled=True,
        leaf_a={"lang": "English", "term": "gift"},
        leaf_b={"lang": "German", "term": "Gift"},
        answer_graph={"nodes": [], "edges": []},
        choices=cast(list[dict[str, Any]], ["not a choice"]),
        correct_choice="c0",
        quality_score=4,
        lang_pair="de-en",
    )

    errors = validate_puzzles([p])

    assert any("choices must contain objects" in error for error in errors)
    assert any("answer graph must have" in error for error in errors)


def test_from_dict_round_trips_answer_only():
    answer = {
        "nodes": [
            {"id": "English:gift", "role": "leaf"},
            {"id": "German:Gift", "role": "leaf"},
            {"id": "Proto-Germanic:*giftiz", "role": "ancestor"},
        ],
        "edges": [{"from": "English:gift", "to": "Proto-Germanic:*giftiz"}],
    }
    data = {
        "id": "a" * 32,
        "enabled": True,
        "leaf_a": {"lang": "English", "term": "gift"},
        "leaf_b": {"lang": "German", "term": "Gift"},
        "answer_graph": answer,
        "choices": [
            {"id": "c0", "gloss": "something given"},
            {"id": "c1", "gloss": "a beast"},
            {"id": "c2", "gloss": "to die"},
            {"id": "c3", "gloss": "a servant"},
        ],
        "correct_choice": "c0",
        "quality_score": 4,
        "lang_pair": "de-en",
    }
    p = Puzzle.from_dict(data)
    assert p.prompt_graph["edges"] == []
    assert {n["id"] for n in p.prompt_graph["nodes"]} == {n["id"] for n in answer["nodes"]}
    assert "prompt_graph" not in p.to_dict()


def test_from_dict_rejects_stored_prompt_graph():
    answer = {
        "nodes": [{"id": "English:gift", "role": "leaf"}, {"id": "German:Gift", "role": "leaf"}],
        "edges": [{"from": "English:gift", "to": "German:Gift"}],
    }
    data = {
        "id": "a" * 32,
        "leaf_a": {"lang": "English", "term": "gift"},
        "leaf_b": {"lang": "German", "term": "Gift"},
        "prompt_graph": {"nodes": answer["nodes"], "edges": []},
        "answer_graph": answer,
        "choices": [{"id": "c0", "gloss": "x"}] * 4,
        "correct_choice": "c0",
        "lang_pair": "de-en",
    }
    with pytest.raises(ValueError, match="prompt_graph is not stored"):
        Puzzle.from_dict(data)
