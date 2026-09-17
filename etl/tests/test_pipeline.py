from typing import Any, cast

import pandas as pd
import pytest

from etl.derive import (
    etymology_parent_terms,
    first_gloss,
    gloss_for,
    index_gloss_objects,
    is_grammatical_gloss,
    is_junk_term,
    is_redirect_gloss,
    reduce_edges,
)
from etl.generate import (
    Funnel,
    build_graph,
    extract_candidates,
    involves_english,
    is_proper_noun_leaf,
    leaf_reuse_key,
    make_choices,
    meaning_overlap,
    normalize_label,
    prefer_latin_chain_path,
    prepare_score_buckets,
    quality_score,
    shares_meaning,
)
from etl.ids import puzzle_id
from etl.validate import validate_puzzles
from etl.models import Puzzle, node_id


def test_first_gloss_joins_colon_qualifier():
    assert first_gloss(
        {
            "senses": [
                {
                    "glosses": [
                        "Of a person:",
                        "Complacent, self-satisfied, smug.",
                    ]
                }
            ]
        }
    ) == "Of a person: Complacent, self-satisfied, smug."
    assert (
        first_gloss({"senses": [{"glosses": ["noble or divine woman :", "goddess"]}]})
        == "noble or divine woman : goddess"
    )


def test_first_gloss_keeps_single_complete_string():
    assert first_gloss({"senses": [{"glosses": ["a present given to someone"]}]}) == (
        "a present given to someone"
    )
    assert first_gloss({"senses": [{"glosses": ["a dog", "a hound"]}]}) == "a dog"


def test_first_gloss_skips_inflection_senses():
    inflection = {
        "glosses": ["inflection of dō:", "present active infinitive"],
        "form_of": [{"word": "dō"}],
    }
    assert first_gloss({"senses": [inflection]}) is None
    assert first_gloss(
        {"senses": [{"glosses": ["Inflection of ābīdan:", "first-person singular present indicative"]}]}
    ) is None
    assert (
        first_gloss(
            {
                "senses": [
                    inflection,
                    {"glosses": ["to give"]},
                ]
            }
        )
        == "to give"
    )
    assert (
        first_gloss(
            {
                "senses": [
                    {
                        "glosses": ["alternative form of foo"],
                        "form_of": [{"word": "foo"}],
                    },
                    {"glosses": ["a courtyard"]},
                ]
            }
        )
        == "a courtyard"
    )


def test_first_gloss_skips_grammatical_forms_without_form_of():
    assert first_gloss({"senses": [{"glosses": ["present active infinitive of superō"]}]}) is None
    assert first_gloss(
        {
            "senses": [
                {
                    "glosses": ["accusative/ablative singular of tū"],
                    "tags": ["accusative", "form-of"],
                }
            ]
        }
    ) is None
    assert first_gloss({"senses": [{"glosses": ["alternative form of foo"]}]}) is None
    assert first_gloss({"senses": [{"glosses": ["synonym of bar"]}]}) is None
    assert first_gloss(
        {
            "senses": [
                {
                    "glosses": [
                        "One of a number of alternative forms of the same gene occupying a given position."
                    ]
                }
            ]
        }
    ) == ("One of a number of alternative forms of the same gene occupying a given position.")
    assert not is_redirect_gloss(
        "One of a number of alternative forms of the same gene occupying a given position."
    )
    assert is_redirect_gloss("Alternative form of acromegaly.")
    assert is_redirect_gloss("synonym of canō (“to sing”)")
    assert (
        first_gloss({"senses": [{"glosses": ["masculine, male (of humans or animals)"]}]})
        == "masculine, male (of humans or animals)"
    )
    assert not is_grammatical_gloss("masculine, male (of humans or animals)")
    assert not is_grammatical_gloss("present, a gift given to someone")
    assert is_grammatical_gloss("present active infinitive of superō")
    assert first_gloss({"senses": [{"glosses": ["[with genitive]", "through"]}]}) == "through"
    assert (
        first_gloss({"senses": [{"glosses": ["[of place] above; over; on the top of; upon"]}]})
        == "above; over; on the top of; upon"
    )
    assert first_gloss({"senses": [{"glosses": ["[with genitive]"]}]}) is None
    assert is_grammatical_gloss("[with genitive]")
    assert not is_grammatical_gloss("[α]_D, the angle of rotation")


def test_index_glosses_inherits_form_only_lemma():
    glosses, lemmas, _parents = index_gloss_objects(
        [
            {
                "lang": "Latin",
                "word": "addere",
                "senses": [
                    {
                        "glosses": ["present active infinitive of addō"],
                        "form_of": [{"word": "addō"}],
                    }
                ],
            },
            {
                "lang": "Latin",
                "word": "superare",
                "senses": [{"glosses": ["present active infinitive of superō"]}],
            },
            {
                "lang": "Latin",
                "word": "addō",
                "senses": [{"glosses": ["to add, attach, join"]}],
            },
            {
                "lang": "Latin",
                "word": "supero",
                "senses": [{"glosses": ["to overcome, surpass"]}],
            },
            {
                "lang": "Old French",
                "word": "amirail",
                "senses": [{"glosses": ["alternative form of amiral"]}],
            },
            {
                "lang": "Old French",
                "word": "amiral",
                "senses": [{"glosses": ["naval commander"]}],
            },
            {
                "lang": "Latin",
                "word": "lacertus",
                "senses": [{"glosses": ["alternative form of lacerta: a lizard"]}],
            },
        ]
    )
    assert glosses["Latin\taddō"] == "to add, attach, join"
    assert glosses["Latin\taddere"] == "to add, attach, join"
    assert lemmas["Latin\taddere"] == "addō"
    assert glosses["Latin\tsuperare"] == "to overcome, surpass"
    assert lemmas["Latin\tsuperare"] == "supero"
    assert glosses["Old French\tamirail"] == "naval commander"
    assert "Old French\tamirail" not in lemmas
    assert glosses["Latin\tlacertus"] == "a lizard"
    assert "Latin\tlacertus" not in lemmas
    assert gloss_for(glosses, "Old French", "amirail") == "naval commander"
    # Leftover stub in an old index is unwrapped at lookup time.
    stale = dict(glosses)
    stale["English\tacromegalia"] = "Alternative form of acromegaly."
    stale["English\tacromegaly"] = "abnormal growth of the extremities"
    assert gloss_for(stale, "English", "acromegalia") == "abnormal growth of the extremities"
    assert gloss_for(stale, "English", "missing") is None
    assert gloss_for({"English\tstub": "alternative form of nowhere"}, "English", "stub") is None
    # Late/Medieval Latin nodes reuse Classical Latin kaikki glosses; macrons fold.
    assert gloss_for({"Latin\thaeresis": "sect"}, "Medieval Latin", "haeresis") == "sect"
    assert gloss_for({"Latin\tmuseum": "temple of the Muses"}, "Latin", "mūsēum") == "temple of the Muses"
    assert gloss_for({"Latin\toeconomus": "steward"}, "Late Latin", "oeconomus") == "steward"


def test_index_glosses_keeps_lexical_homograph_not_lemma():
    """Latin factum has a noun sense; do not redirect to faciō."""
    glosses, lemmas, _parents = index_gloss_objects(
        [
            {
                "lang": "Latin",
                "word": "factum",
                "senses": [
                    {
                        "glosses": ["accusative supine of faciō and fīō"],
                        "form_of": [{"word": "faciō and fīō"}],
                    }
                ],
            },
            {
                "lang": "Latin",
                "word": "factum",
                "senses": [{"glosses": ["fact, deed, act, doing, work"]}],
            },
            {
                "lang": "Latin",
                "word": "faciō",
                "senses": [{"glosses": ["to do, to make"]}],
            },
        ]
    )
    assert glosses["Latin\tfactum"] == "fact, deed, act, doing, work"
    assert "Latin\tfactum" not in lemmas
    assert lemmas == {}


def test_etymology_parent_terms_ignores_etymon_and_reads_arg3():
    terms = etymology_parent_terms(
        {
            "etymology_templates": [
                {"name": "etymon", "args": {"1": "en", "3": "ignored"}},
                {"name": "inh", "args": {"1": "en", "2": "ang", "3": "sunu"}},
                {"name": "inh", "args": {"1": "en", "2": "gem-pro", "3": "*sunuz"}},
                {"name": "bor", "args": {"1": "en", "2": "es", "3": "son"}},
                {"name": "der", "args": {"1": "en", "2": "ine-pro", "3": "*sewH-"}},
                {"name": "root", "args": {1: "en", 2: "ine-pro", 3: "*sewH-"}},
            ]
        }
    )
    assert terms == ["sunu", "*sunuz", "son", "*sewH-"]


def test_index_glosses_parents_come_from_winning_etymology_only():
    glosses, _lemmas, parents = index_gloss_objects(
        [
            {
                "lang": "English",
                "word": "son",
                "senses": [{"glosses": ["One's male offspring."]}],
                "etymology_templates": [
                    {"name": "inh", "args": {"1": "en", "2": "ang", "3": "sunu"}},
                ],
            },
            {
                "lang": "English",
                "word": "son",
                "senses": [{"glosses": ["Son cubano, a genre of music."]}],
                "etymology_templates": [
                    {"name": "bor", "args": {"1": "en", "2": "es", "3": "son"}},
                ],
            },
        ]
    )
    assert glosses["English\tson"] == "One's male offspring."
    assert parents["English\tson"] == ["sunu"]


def test_index_glosses_does_not_copy_parents_onto_form_only_lemmas():
    _glosses, lemmas, parents = index_gloss_objects(
        [
            {
                "lang": "Latin",
                "word": "addere",
                "senses": [
                    {
                        "glosses": ["present active infinitive of addō"],
                        "form_of": [{"word": "addō"}],
                    }
                ],
            },
            {
                "lang": "Latin",
                "word": "addō",
                "senses": [{"glosses": ["to add, attach, join"]}],
                "etymology_templates": [
                    {"name": "inh", "args": {"1": "la", "2": "itc-pro", "3": "*ad-dō"}},
                ],
            },
        ]
    )
    assert lemmas["Latin\taddere"] == "addō"
    assert parents["Latin\taddō"] == ["*ad-dō"]
    assert "Latin\taddere" not in parents


def _reduce_cfg() -> dict[str, Any]:
    return {
        "leaf_languages": {"English": "en", "Spanish": "es", "Portuguese": "pt", "German": "de"},
        "ancestor_languages": ["Old English", "Proto-Germanic", "Latin"],
        "keep_reltypes": [
            "inherited_from",
            "borrowed_from",
            "derived_from",
            "root",
            "cognate_of",
        ],
        "ancestor_reltypes": ["inherited_from", "borrowed_from", "derived_from", "root"],
    }


def test_reduce_edges_drops_unaligned_borrow_keeps_cognate():
    df = pd.DataFrame(
        [
            dict(term="son", lang="English", reltype="inherited_from", related_term="sunu", related_lang="Old English"),
            dict(term="son", lang="English", reltype="borrowed_from", related_term="son", related_lang="Spanish"),
            dict(term="son", lang="English", reltype="cognate_of", related_term="Sohn", related_lang="German"),
        ]
    )
    out = reduce_edges(df, _reduce_cfg(), parents={"English\tson": ["sunu", "*sunuz"]})
    pairs = set(zip(out["reltype"], out["related_term"], out["related_lang"]))
    assert ("inherited_from", "sunu", "Old English") in pairs
    assert ("borrowed_from", "son", "Spanish") not in pairs
    assert ("cognate_of", "Sohn", "German") in pairs


def test_reduce_edges_keeps_latin_intermediate_on_path_to_allowlisted_greek():
    """Templates naming only Greek must not drop a dump Latin hop that reaches Greek."""
    cfg = {
        **_reduce_cfg(),
        "ancestor_languages": ["Latin", "Ancient Greek", "Old English", "Proto-Germanic"],
    }
    df = pd.DataFrame(
        [
            dict(term="historia", lang="Spanish", reltype="borrowed_from", related_term="historia", related_lang="Latin"),
            dict(term="historia", lang="Spanish", reltype="derived_from", related_term="ἱστορία", related_lang="Ancient Greek"),
            dict(term="historia", lang="Latin", reltype="derived_from", related_term="ἱστορία", related_lang="Ancient Greek"),
            # Homograph noise: must still drop when not on a path to the allowlist.
            dict(term="son", lang="English", reltype="inherited_from", related_term="sunu", related_lang="Old English"),
            dict(term="son", lang="English", reltype="borrowed_from", related_term="son", related_lang="Spanish"),
        ]
    )
    out = reduce_edges(
        df,
        cfg,
        parents={
            "Spanish\thistoria": ["ἱστορία"],
            "English\tson": ["sunu", "*sunuz"],
        },
    )
    pairs = set(zip(out["lang"], out["reltype"], out["related_term"], out["related_lang"]))
    assert ("Spanish", "borrowed_from", "historia", "Latin") in pairs
    assert ("Spanish", "derived_from", "ἱστορία", "Ancient Greek") in pairs
    assert ("English", "inherited_from", "sunu", "Old English") in pairs
    assert ("English", "borrowed_from", "son", "Spanish") not in pairs


def test_reduce_edges_macron_fold_matches_allowlist():
    cfg = {
        **_reduce_cfg(),
        "ancestor_languages": ["Latin", "Ancient Greek"],
    }
    df = pd.DataFrame(
        [
            dict(term="pulpo", lang="Spanish", reltype="inherited_from", related_term="polypūs", related_lang="Latin"),
            dict(term="pulpo", lang="Spanish", reltype="derived_from", related_term="πολύπους", related_lang="Ancient Greek"),
        ]
    )
    out = reduce_edges(df, cfg, parents={"Spanish\tpulpo": ["polypus", "πολύπους"]})
    pairs = set(zip(out["reltype"], out["related_term"], out["related_lang"]))
    assert ("inherited_from", "polypūs", "Latin") in pairs
    assert ("derived_from", "πολύπους", "Ancient Greek") in pairs


def test_reduce_edges_falls_back_when_allowlist_matches_nothing():
    df = pd.DataFrame(
        [
            dict(term="foo", lang="English", reltype="inherited_from", related_term="bar", related_lang="Latin"),
        ]
    )
    out = reduce_edges(df, _reduce_cfg(), parents={"English\tfoo": ["zzz"]})
    assert len(out) == 1
    assert out.iloc[0]["related_term"] == "bar"


def test_extract_candidates_son_does_not_walk_spanish_borrow():
    rows = [
        dict(term="son", lang="English", reltype="inherited_from", related_term="sunu", related_lang="Old English"),
        dict(term="son", lang="English", reltype="borrowed_from", related_term="son", related_lang="Spanish"),
        dict(term="sunu", lang="Old English", reltype="inherited_from", related_term="*sunuz", related_lang="Proto-Germanic"),
        dict(term="Sohn", lang="German", reltype="inherited_from", related_term="*sunuz", related_lang="Proto-Germanic"),
        dict(term="son", lang="Spanish", reltype="derived_from", related_term="sonus", related_lang="Latin"),
        dict(term="sónico", lang="Spanish", reltype="derived_from", related_term="sonus", related_lang="Latin"),
    ]
    df = reduce_edges(
        pd.DataFrame(rows),
        _reduce_cfg(),
        parents={"English\tson": ["sunu", "*sunuz"]},
    )
    glosses = {
        "English\tson": "One's male offspring.",
        "German\tSohn": "a boy relative of his parents",
        "Spanish\tsónico": "sonic",
        "Old English\tsunu": "a male child",
        "Proto-Germanic\t*sunuz": "a male descendant in a family line",
        "Latin\tsonus": "sound, noise; pitch",
        "Spanish\tson": "a musical genre; a pleasant sound",
    }
    g = build_graph(df, {"inherited_from", "borrowed_from", "derived_from", "root"})
    cfg = {
        "leaf_languages": {"English": "en", "Spanish": "es", "Portuguese": "pt", "German": "de"},
        "ancestor_reltypes": ["inherited_from", "borrowed_from", "derived_from", "root"],
        "generate": {"max_nodes": 9, "max_gloss_overlap": 0.5},
    }
    funnel = Funnel()
    cands = extract_candidates(g, glosses, cfg, funnel)
    son_pairs = [
        c
        for c in cands
        if {c["leaf_a"]["term"], c["leaf_b"]["term"]} == {"son", "Sohn"}
        and {c["leaf_a"]["lang"], c["leaf_b"]["lang"]} == {"English", "German"}
    ]
    assert son_pairs, f"expected son/Sohn candidate, got {[(c['leaf_a'], c['leaf_b'], c['lca']) for c in cands]}"
    gold = {(e.source, e.target) for e in son_pairs[0]["edges"]}
    assert ("English:son", "Spanish:son") not in gold
    assert son_pairs[0]["lca"]["term"] == "*sunuz"
    mixed = [
        c
        for c in cands
        if {node_id(c["leaf_a"]["lang"], c["leaf_a"]["term"]), node_id(c["leaf_b"]["lang"], c["leaf_b"]["term"])}
        == {"English:son", "Spanish:sónico"}
    ]
    assert mixed == []


def test_extract_candidates_routes_parallel_der_through_late_latin():
    """BFS leaf→Greek shortcut becomes leaf→Late Latin→Greek when both edges exist."""
    rows = [
        dict(term="Ökonom", lang="German", reltype="derived_from", related_term="oeconomus", related_lang="Late Latin"),
        dict(term="Ökonom", lang="German", reltype="derived_from", related_term="οἰκονόμος", related_lang="Ancient Greek"),
        dict(
            term="económico",
            lang="Portuguese",
            reltype="derived_from",
            related_term="oeconomicus",
            related_lang="Latin",
        ),
        dict(
            term="oeconomicus",
            lang="Latin",
            reltype="derived_from",
            related_term="οἰκονόμος",
            related_lang="Ancient Greek",
        ),
    ]
    df = pd.DataFrame(rows)
    glosses = {
        "German\tÖkonom": "economist",
        "Portuguese\teconómico": "economic",
        "Late Latin\toeconomus": "steward of a household",
        "Latin\toeconomicus": "of household management",
        "Ancient Greek\tοἰκονόμος": "one who manages a household",
    }
    g = build_graph(df, {"inherited_from", "borrowed_from", "derived_from", "root"})
    cfg = {
        "leaf_languages": {"English": "en", "Spanish": "es", "Portuguese": "pt", "German": "de"},
        "ancestor_reltypes": ["inherited_from", "borrowed_from", "derived_from", "root"],
        "generate": {"max_nodes": 9, "max_gloss_overlap": 0.5},
    }
    funnel = Funnel()
    cands = extract_candidates(g, glosses, cfg, funnel)
    assert len(cands) == 1
    gold = {(e.source, e.target) for e in cands[0]["edges"]}
    assert ("German:Ökonom", "Late Latin:oeconomus") in gold
    assert ("Late Latin:oeconomus", "Ancient Greek:οἰκονόμος") in gold
    assert ("German:Ökonom", "Ancient Greek:οἰκονόμος") not in gold
    assert ("Portuguese:económico", "Latin:oeconomicus") in gold
    assert cands[0]["lca"]["term"] == "οἰκονόμος"
    # Direct unit check: prefer_latin_chain_path invents Latin→LCA when missing.
    path = prefer_latin_chain_path(g, ["German:Ökonom", "Ancient Greek:οἰκονόμος"], "Ancient Greek:οἰκονόμος")
    assert path == ["German:Ökonom", "Late Latin:oeconomus", "Ancient Greek:οἰκονόμος"]


def test_first_gloss_empty_or_missing_senses():
    assert first_gloss({}) is None
    assert first_gloss({"senses": []}) is None
    assert first_gloss({"senses": [{"glosses": []}]}) is None
    assert first_gloss({"senses": [{"glosses": ["  "]}]}) is None


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


def test_meaning_overlap_helpers():
    assert normalize_label("*Gift") == "gift"
    assert meaning_overlap("a dog used for hunting", "a dog") > 0.2
    assert meaning_overlap("a present given to someone", "poison; a toxic substance") < 0.2
    assert shares_meaning("dog", "a dog used for hunting")
    assert shares_meaning("Gift", "a gift; something given")
    assert not shares_meaning("gift", "poison; a toxic substance")
    assert not shares_meaning("the", "the ancestor sense")
    # Headword identity (lca_equals_leaf): first content word of term/gloss.
    assert shares_meaning("gift", "gift", head_only=True)
    assert shares_meaning("Gift", "*gift", head_only=True)
    assert shares_meaning("a toxic substance", "a toxic substance", head_only=True)
    assert shares_meaning("hound", "hound", head_only=True)
    assert shares_meaning("dragon", "dragon, monster", head_only=True)
    assert shares_meaning("dragon", "a dragon or monster", head_only=True)
    assert not shares_meaning("gift", "poison", head_only=True)
    assert not shares_meaning("present", "something given", head_only=True)


def test_puzzle_id_order_invariant():
    a = {"lang": "English", "term": "gift"}
    b = {"lang": "German", "term": "Gift"}
    lca = {"lang": "Proto-Germanic", "term": "*giftiz"}
    e1 = [{"from": "English:gift", "to": "Proto-Germanic:*giftiz"}]
    e2 = [{"from": "German:Gift", "to": "Proto-Germanic:*giftiz"}]
    assert puzzle_id(a, b, lca, e1 + e2) == puzzle_id(b, a, lca, list(reversed(e1 + e2)))


def test_quality_score_is_integer_rubric():
    base: dict[str, Any] = dict(
        high_overlap=False, lca_is_modern=False, term_a="alpha", term_b="omega"
    )
    assert quality_score(lang_a="English", lang_b="German", **base) == 5
    assert quality_score(lang_a="English", lang_b="English", **base) == 2  # −3 same-lang
    # Spanish–Portuguese only penalized when leaf terms share a 3-char prefix (−2).
    assert quality_score(lang_a="Spanish", lang_b="Portuguese", **base) == 5
    assert (
        quality_score(
            lang_a="Spanish",
            lang_b="Portuguese",
            **{**base, "term_a": "hombre", "term_b": "homem"},
        )
        == 3
    )
    assert quality_score(lang_a="English", lang_b="German", **{**base, "lca_is_modern": True}) == 4
    assert quality_score(lang_a="English", lang_b="German", **{**base, "high_overlap": True}) == 4
    worst_cross = quality_score(
        lang_a="Spanish",
        lang_b="Portuguese",
        term_a="hombre",
        term_b="homem",
        high_overlap=True,
        lca_is_modern=True,
    )
    assert worst_cross == 1
    assert isinstance(worst_cross, int)
    assert (
        quality_score(
            lang_a="English",
            lang_b="English",
            term_a="gift",
            term_b="present",
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
        [
            "sense a",
            "sense b",
            "sense c",
            "ancestor gloss",
            "alternative form of cappa",
            "synonym of canō",
        ],
        n_choices=4,
        rng=rng,
    )
    assert built is not None
    choices, correct_id = built
    glosses = [choice["gloss"] for choice in choices]
    assert len(glosses) == 4
    assert len(set(glosses)) == 4
    assert all(not g.startswith("(unrelated)") for g in glosses)
    assert all(not is_redirect_gloss(g) for g in glosses)
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
            "min_quality": 3,
            "n_choices": 4,
            "seed": 1,
            "n": 10,
            "max_nodes": 9,
            "max_gloss_overlap": 0.5,
        },
    }
    return g, glosses, cfg


def test_extract_candidates_early_exit_respects_limit():
    import random as random_mod

    g, glosses, cfg = _synth_shift_graph(400, shared_ancestors=10)
    funnel = Funnel()
    rng = random_mod.Random(1)
    cands = extract_candidates(g, glosses, cfg, funnel, limit=10, min_quality=3, rng=rng)
    assert len(cands) >= 10
    quality = [c for c in cands if c["quality_score"] >= 3]
    assert len(quality) >= 10
    assert funnel.counts.get("early_exit", 0) == 1
    # Without early exit this graph considers tens of thousands of related pairs.
    assert funnel.counts["pairs_considered"] < 5000
    # Per-bucket headroom: finite limit must still pull non-English pairs, not only de-en.
    assert any(involves_english(c) for c in quality)
    assert any(not involves_english(c) for c in quality)

    # Emit buckets: seeded shuffle + English/other water-fill (not alpha A-words first).
    # Simulate leaf-reuse greedily over prepared buckets.
    en_terms_alpha = sorted(
        {
            c["leaf_a"]["term"] if c["leaf_a"]["lang"] == "English" else c["leaf_b"]["term"]
            for c in quality
            if involves_english(c)
        }
    )
    assert en_terms_alpha, "expected English-involving quality candidates"

    def _simulate_emit(seed: int, n: int = 20) -> list[dict]:
        buckets = prepare_score_buckets(quality, random_mod.Random(seed))
        used: set[str] = set()
        out: list[dict] = []
        for en_bucket, other_bucket in buckets:
            en_i = other_i = 0
            emitted_en = emitted_other = 0
            while en_i < len(en_bucket) or other_i < len(other_bucket):
                if len(out) >= n:
                    break
                prefer_en = emitted_en <= emitted_other

                def _take(cand: dict) -> bool:
                    ka = leaf_reuse_key(cand["leaf_a"]["lang"], cand["leaf_a"]["term"])
                    kb = leaf_reuse_key(cand["leaf_b"]["lang"], cand["leaf_b"]["term"])
                    if ka in used or kb in used:
                        return False
                    used.add(ka)
                    used.add(kb)
                    out.append(cand)
                    return True

                if prefer_en and en_i < len(en_bucket):
                    if _take(en_bucket[en_i]):
                        emitted_en += 1
                    en_i += 1
                elif other_i < len(other_bucket):
                    if _take(other_bucket[other_i]):
                        emitted_other += 1
                    other_i += 1
                elif en_i < len(en_bucket):
                    if _take(en_bucket[en_i]):
                        emitted_en += 1
                    en_i += 1
                else:
                    break
            if len(out) >= n:
                break
        return out

    batch = _simulate_emit(1, n=20)
    en_n = sum(1 for c in batch if involves_english(c))
    other_n = len(batch) - en_n
    assert en_n >= 1 and other_n >= 1
    assert abs(en_n - other_n) <= 1

    first_en = next(
        (
            c["leaf_a"]["term"] if c["leaf_a"]["lang"] == "English" else c["leaf_b"]["term"]
            for c in batch
            if involves_english(c)
        ),
        None,
    )
    assert first_en is not None
    # A-words must not lead: first emitted English leaf is not the alphabetically first.
    assert first_en != en_terms_alpha[0] or len(en_terms_alpha) == 1

    pairs_s1 = {
        tuple(sorted([(c["leaf_a"]["lang"], c["leaf_a"]["term"]), (c["leaf_b"]["lang"], c["leaf_b"]["term"])]))
        for c in _simulate_emit(1, n=20)
    }
    pairs_s2 = {
        tuple(sorted([(c["leaf_a"]["lang"], c["leaf_a"]["term"]), (c["leaf_b"]["lang"], c["leaf_b"]["term"])]))
        for c in _simulate_emit(2, n=20)
    }
    assert pairs_s1 != pairs_s2


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
            "max_nodes": 9,
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
            "max_nodes": 9,
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


def test_extract_candidates_rewrites_form_only_lca_to_lemma():
    """Form-only Latin infinitive LCA is replaced by the citation verb."""
    rows = [
        dict(term="additive", lang="English", reltype="derived_from", related_term="addere", related_lang="Latin"),
        dict(term="addieren", lang="German", reltype="derived_from", related_term="addere", related_lang="Latin"),
    ]
    glosses = {
        "English\tadditive": "a substance mixed into food",
        "German\taddieren": "perform arithmetic summation",
        "Latin\taddere": "to add, attach, join",
        "Latin\taddō": "to add, attach, join",
    }
    lemmas = {"Latin\taddere": "addō"}
    g = build_graph(pd.DataFrame(rows), {"derived_from"})
    cfg = {
        "leaf_languages": {"English": "en", "Spanish": "es", "Portuguese": "pt", "German": "de"},
        "ancestor_reltypes": ["derived_from"],
        "generate": {
            "max_nodes": 9,
            "max_gloss_overlap": 0.5,
        },
    }
    funnel = Funnel()
    cands = extract_candidates(g, glosses, cfg, funnel, lemmas=lemmas)
    assert len(cands) == 1
    lca = cands[0]["lca"]
    assert lca["lang"] == "Latin"
    assert lca["term"] == "addō"
    assert lca["gloss"] == "to add, attach, join"
    assert lca["id"] == "Latin:addō"
    assert "Latin:addere" not in cands[0]["nodes"]
    assert "Latin:addō" in cands[0]["nodes"]

    # Alt-form LCAs keep the surface spelling; only the meaning is inherited.
    # lemma_index must not rewrite amirail → amiral.
    rows_alt = [
        dict(term="admiral", lang="English", reltype="derived_from", related_term="amirail", related_lang="Old French"),
        dict(term="Admiral", lang="German", reltype="derived_from", related_term="amirail", related_lang="Old French"),
    ]
    glosses_alt = {
        "English\tadmiral": "fleet flag officer in modern navies",
        "German\tAdmiral": "high ranking sea officer",
        "Old French\tamirail": "commander of a medieval fleet",
        "Old French\tamiral": "commander of a medieval fleet",
    }
    g_alt = build_graph(pd.DataFrame(rows_alt), {"derived_from"})
    funnel_alt = Funnel()
    cands_alt = extract_candidates(g_alt, glosses_alt, cfg, funnel_alt, lemmas={})
    assert len(cands_alt) == 1
    assert cands_alt[0]["lca"]["term"] == "amirail"
    assert cands_alt[0]["lca"]["gloss"] == "commander of a medieval fleet"
    assert cands_alt[0]["lca"]["id"] == "Old French:amirail"


def test_extract_candidates_keeps_lexical_homograph_lca():
    """factum with a noun gloss is not rewritten to faciō."""
    rows = [
        dict(term="factoid", lang="English", reltype="derived_from", related_term="factum", related_lang="Latin"),
        dict(term="Faktum", lang="German", reltype="derived_from", related_term="factum", related_lang="Latin"),
    ]
    glosses = {
        "English\tfactoid": "a dubious or insignificant fact",
        "German\tFaktum": "something concrete used as a basis for interpretation",
        "Latin\tfactum": "deed, act, doing, work",
        "Latin\tfaciō": "to do, to make",
    }
    g = build_graph(pd.DataFrame(rows), {"derived_from"})
    cfg = {
        "leaf_languages": {"English": "en", "Spanish": "es", "Portuguese": "pt", "German": "de"},
        "ancestor_reltypes": ["derived_from"],
        "generate": {
            "max_nodes": 9,
            "max_gloss_overlap": 0.5,
        },
    }
    funnel = Funnel()
    cands = extract_candidates(g, glosses, cfg, funnel, lemmas={})
    assert len(cands) == 1
    assert cands[0]["lca"]["term"] == "factum"
    assert cands[0]["lca"]["gloss"] == "deed, act, doing, work"


@pytest.mark.parametrize(
    "lca_term,lca_gloss",
    [
        ("fare", "second-person singular present active indicative of for"),
        ("huper", "[with genitive]"),
        ("amirail", "alternative form of missing"),
    ],
)
def test_extract_candidates_rejects_leftover_grammatical_lca_gloss(lca_term, lca_gloss):
    rows = [
        dict(term="leafx", lang="English", reltype="inherited_from", related_term=lca_term, related_lang="Latin"),
        dict(term="leafy", lang="German", reltype="inherited_from", related_term=lca_term, related_lang="Latin"),
    ]
    glosses = {
        "English\tleafx": "modern sense alpha zebra",
        "German\tleafy": "modern sense beta quartz",
        f"Latin\t{lca_term}": lca_gloss,
    }
    g = build_graph(pd.DataFrame(rows), {"inherited_from"})
    funnel = Funnel()
    cands = extract_candidates(g, glosses, _two_leaf_lca_cfg(), funnel)
    assert cands == []
    # Grammatical leftovers use inflection_lca; unresolved redirects become no_gloss.
    assert (
        funnel.counts.get("inflection_lca", 0) >= 1
        or funnel.counts.get("no_gloss", 0) >= 1
    )
    assert funnel.counts.get("candidates", 0) == 0


def test_extract_candidates_rejects_leaf_term_in_lca_gloss():
    """Both leaves still same meaning when each term appears in the LCA gloss."""
    rows = [
        dict(term="hound", lang="English", reltype="inherited_from", related_term="*hundaz", related_lang="Proto-Germanic"),
        dict(term="Hund", lang="German", reltype="inherited_from", related_term="*hundaz", related_lang="Proto-Germanic"),
    ]
    glosses = {
        "English\thound": "a hunting dog",
        "German\tHund": "a domestic animal",
        "Proto-Germanic\t*hundaz": "an animal such as a hound or hund",
    }
    g = build_graph(pd.DataFrame(rows), {"inherited_from"})
    funnel = Funnel()
    cands = extract_candidates(g, glosses, _two_leaf_lca_cfg(), funnel)
    assert cands == []
    assert funnel.counts.get("same_meaning", 0) >= 1
    assert funnel.counts.get("candidates", 0) == 0


@pytest.mark.parametrize(
    "leaf_a,leaf_b,lca_term,glosses,reason",
    [
        (
            ("gift", "English"),
            ("Gift", "German"),
            "*giftiz",
            {
                "English\tgift": "present",
                "German\tGift": "poison",
                "Proto-Germanic\t*giftiz": "present",
            },
            "leaf gloss equals LCA gloss",
        ),
        (
            ("gift", "English"),
            ("Gift", "German"),
            "gift",
            {
                "English\tgift": "modern sense alpha zebra",
                "German\tGift": "modern sense beta quartz",
                "Proto-Germanic\tgift": "ancient root poison venom",
            },
            "leaf term equals LCA term",
        ),
        (
            ("hound", "English"),
            ("Hund", "German"),
            "*hundaz",
            {
                "English\thound": "a hunting dog",
                "German\tHund": "a domestic animal",
                "Proto-Germanic\t*hundaz": "hound",
            },
            "leaf term equals LCA gloss",
        ),
        (
            ("gift", "English"),
            ("Gift", "German"),
            "*giftiz",
            {
                "English\tgift": "giftiz",
                "German\tGift": "modern sense beta quartz",
                "Proto-Germanic\t*giftiz": "ancient root poison venom",
            },
            "leaf gloss equals LCA term",
        ),
    ],
)
def test_extract_candidates_rejects_leaf_equal_to_lca(leaf_a, leaf_b, lca_term, glosses, reason):
    """Hard-reject when a leaf term or gloss is identical to the LCA term or gloss."""
    term_a, lang_a = leaf_a
    term_b, lang_b = leaf_b
    rows = [
        dict(term=term_a, lang=lang_a, reltype="inherited_from", related_term=lca_term, related_lang="Proto-Germanic"),
        dict(term=term_b, lang=lang_b, reltype="inherited_from", related_term=lca_term, related_lang="Proto-Germanic"),
    ]
    g = build_graph(pd.DataFrame(rows), {"inherited_from"})
    funnel = Funnel()
    cands = extract_candidates(g, glosses, _two_leaf_lca_cfg(), funnel)
    assert cands == [], reason
    assert funnel.counts.get("lca_equals_leaf", 0) >= 1, reason
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


def _long_lca_pair(n_en_inter: int, n_de_inter: int) -> tuple[pd.DataFrame, dict[str, str]]:
    """Two leaves chained through unused ancestor langs to a shared Proto-Germanic LCA."""
    inter_langs = [
        "Old English",
        "Latin",
        "Ancient Greek",
        "Arabic",
        "Sanskrit",
        "Persian",
        "Hebrew",
        "Gothic",
    ]
    rows: list[dict[str, str]] = []
    glosses = {
        "English\tleafx": "modern sense alpha zebra",
        "German\tleafy": "modern sense beta quartz",
        "Proto-Germanic\trootx": "ancient root poison venom",
    }

    def chain(leaf_term: str, leaf_lang: str, n_inter: int, prefix: str) -> None:
        prev_term, prev_lang = leaf_term, leaf_lang
        for i in range(n_inter):
            term, lang = f"{prefix}{i}xx", inter_langs[i]
            rows.append(
                dict(
                    term=prev_term,
                    lang=prev_lang,
                    reltype="inherited_from",
                    related_term=term,
                    related_lang=lang,
                )
            )
            prev_term, prev_lang = term, lang
        rows.append(
            dict(
                term=prev_term,
                lang=prev_lang,
                reltype="inherited_from",
                related_term="rootx",
                related_lang="Proto-Germanic",
            )
        )

    chain("leafx", "English", n_en_inter, "en")
    chain("leafy", "German", n_de_inter, "de")
    return pd.DataFrame(rows), glosses


def test_extract_candidates_rejects_graphs_over_max_nodes():
    """10 unique nodes (2 leaves + 7 intermediates + LCA) exceeds max_nodes=9."""
    df, glosses = _long_lca_pair(4, 3)
    g = build_graph(df, {"inherited_from"})
    funnel = Funnel()
    cands = extract_candidates(g, glosses, _two_leaf_lca_cfg(), funnel)
    assert cands == []
    assert funnel.counts.get("too_big", 0) >= 1
    assert funnel.counts.get("candidates", 0) == 0


def test_extract_candidates_accepts_max_nodes_boundary():
    """9 unique nodes (2 leaves + 6 intermediates + LCA) is allowed."""
    df, glosses = _long_lca_pair(3, 3)
    g = build_graph(df, {"inherited_from"})
    funnel = Funnel()
    cands = extract_candidates(g, glosses, _two_leaf_lca_cfg(), funnel)
    assert len(cands) >= 1
    assert len(cands[0]["nodes"]) == 9
    assert funnel.counts.get("too_big", 0) == 0


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
    assert any("leaves must appear in the graph" in error for error in errors)


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
