from typing import Any, cast

from etl.derive import is_junk_term
from etl.generate import gloss_overlap, make_choices, quality_score, still_same_meaning
from etl.ids import puzzle_id
from etl.validate import validate_puzzles
from etl.models import Puzzle


def test_junk_terms():
    assert is_junk_term(None)
    assert is_junk_term("-ness")
    assert is_junk_term("junk compound")
    assert not is_junk_term("*giftiz")
    assert not is_junk_term("gift")


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
    assert quality_score(lang_a="English", lang_b="English", **base) == 3
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


def test_make_choices_uses_unique_placeholders():
    choices, correct_id = make_choices(
        "ancestor gloss",
        ["(unrelated) sense 1"],
        n_choices=4,
        rng=__import__("random").Random(1),
    )

    glosses = [choice["gloss"] for choice in choices]
    assert len(glosses) == len(set(glosses))
    assert choices[[choice["id"] for choice in choices].index(correct_id)]["gloss"] == "ancestor gloss"


def test_validate_happy_path():
    p = Puzzle(
        id="a" * 32,
        enabled=True,
        leaf_a={"lang": "English", "term": "gift", "gloss": "present"},
        leaf_b={"lang": "German", "term": "Gift", "gloss": "poison"},
        prompt_graph={
            "nodes": [
                {"id": "English:gift", "role": "leaf"},
                {"id": "German:Gift", "role": "leaf"},
                {"id": "Proto-Germanic:*giftiz", "role": "ancestor"},
            ],
            "edges": [],
        },
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


def test_validate_reports_malformed_choices_and_graph_together():
    p = Puzzle(
        id="a" * 32,
        enabled=True,
        leaf_a={"lang": "English", "term": "gift"},
        leaf_b={"lang": "German", "term": "Gift"},
        prompt_graph={"nodes": [], "edges": []},
        answer_graph={"nodes": [], "edges": []},
        choices=cast(list[dict[str, Any]], ["not a choice"]),
        correct_choice="c0",
        quality_score=4,
        lang_pair="de-en",
    )

    errors = validate_puzzles([p])

    assert any("choices must contain objects" in error for error in errors)
    assert any("answer graph must have" in error for error in errors)
