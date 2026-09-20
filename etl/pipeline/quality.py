"""Quality scoring for puzzle candidates (soft divergence axes only).

Hard rejects (short/unglossed/inflection LCA, English term≡LCA gloss, …)
live in ``assess_pair`` below; soft axes in ``quality_score``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from simplemma import lemmatize as _simplemma_lemmatize

from etl.pipeline.gloss import is_grammatical_gloss

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


@lru_cache(maxsize=8192)
def _lemma_en(word: str) -> str:
    """Lemmatize one English token; fall back to the surface form on failure."""
    try:
        return _simplemma_lemmatize(word, lang="en") or word
    except Exception:
        return word


def normalize_label(text: str | None) -> str:
    """Casefold a term or gloss for identity checks; strip a reconstruction *."""
    if not text:
        return ""
    s = text.strip().casefold()
    if s.startswith("*"):
        s = s[1:].lstrip()
    return s


def content_tokens(
    text: str | None, *, head_only: bool = False, lemmatize: bool = False
) -> set[str]:
    """Content tokens after normalize_label; optionally only the first token.

    When ``lemmatize`` is true, each token is reduced to its English lemma
    (used by meaning-overlap checks only).
    """
    tokens = set()
    for word in _iter_content_tokens(normalize_label(text)):
        tokens.add(_lemma_en(word) if lemmatize else word)
        if head_only:
            break
    return tokens


def meaning_overlap(a: str | None, b: str | None, *, head_only: bool = False) -> float:
    """Jaccard of lemmatized content tokens (singletons when head_only). Empty side -> 0.0."""
    ta = content_tokens(a, head_only=head_only, lemmatize=True)
    tb = content_tokens(b, head_only=head_only, lemmatize=True)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def shares_meaning(a: str | None, b: str | None, *, head_only: bool = False) -> bool:
    """True when two labels share any lemmatized content token (first only if head_only)."""
    return meaning_overlap(a, b, head_only=head_only) > 0


def similar_spelling(a: str | None, b: str | None) -> bool:
    """equal after normalize, or both length >= 3 with the same 3-char prefix."""
    na, nb = normalize_label(a), normalize_label(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return len(na) >= 3 and len(nb) >= 3 and na[:3] == nb[:3]


def quality_score(
    *,
    lang_a: str,
    lang_b: str,
    term_a: str,
    term_b: str,
    gloss_a: str | None,
    gloss_b: str | None,
    lca_term: str | None,
    lca_gloss: str | None,
    min_quality: int = 0,
) -> int:
    """Integer 0-5. Start at 5; −1 for each missed divergence axis.

    Axes run cheap-to-expensive. When ``min_quality`` > 0, stop once the score
    cannot meet the threshold (stored score may then be a lower bound).
    """
    score = 5

    # 1. Same language (cheapest)
    if lang_a == lang_b:
        score -= 1
        if score < min_quality:
            return max(0, score)

    # 2. Spelling vs LCA
    na, nb, nl = normalize_label(term_a), normalize_label(term_b), normalize_label(lca_term)
    if na == nl or nb == nl:
        score -= 1
        if score < min_quality:
            return max(0, score)

    # 3. Spelling vs each other
    if similar_spelling(term_a, term_b):
        score -= 1
        if score < min_quality:
            return max(0, score)

    # 4. Meaning vs each other (lemmatized gloss tokens)
    tokens_a = content_tokens(gloss_a, lemmatize=True)
    tokens_b = content_tokens(gloss_b, lemmatize=True)
    if tokens_a and tokens_b and (tokens_a & tokens_b):
        score -= 1
        if score < min_quality:
            return max(0, score)

    # 5. Meaning vs LCA (reuse leaf token sets; lemmatize LCA once)
    tokens_lca = content_tokens(lca_gloss, lemmatize=True)
    if tokens_lca and (
        (tokens_a and (tokens_a & tokens_lca)) or (tokens_b and (tokens_b & tokens_lca))
    ):
        score -= 1

    return max(0, score)


MIN_TERM_LENGTH = 3


@dataclass(frozen=True)
class PairAssessment:
    """Outcome of hard filters + quality scoring for one leaf pair / LCA."""

    reject: str | None = None
    quality: int = 0


def term_too_short(term: str | None) -> bool:
    """True when a headword is missing or shorter than MIN_TERM_LENGTH."""
    if not term:
        return True
    return len(term.strip()) < MIN_TERM_LENGTH


def english_term_is_lca_gloss(lang: str, term: str | None, lca_gloss: str | None) -> bool:
    """True when an English leaf term matches the LCA gloss's first content token.

    Articles / function words are ignored; no lemmatization. So ``tunic`` matches
    ``tunic, robe`` and ``a tunic``. Non-English leaves always return False.
    """
    if lang != "English":
        return False
    term_tokens = content_tokens(term)
    gloss_head = content_tokens(lca_gloss, head_only=True)
    if not term_tokens or not gloss_head:
        return False
    return term_tokens == gloss_head


def lca_structural_reject(lca_term: str | None, lca_gloss: str | None) -> str | None:
    """Funnel reason when the chosen LCA is unusable, or None to continue."""
    if term_too_short(lca_term):
        return "term_too_short"
    if not lca_gloss:
        return "no_gloss"
    if is_grammatical_gloss(lca_gloss):
        return "inflection_lca"
    return None


def assess_pair(
    *,
    lang_a: str,
    lang_b: str,
    term_a: str,
    gloss_a: str | None,
    term_b: str,
    gloss_b: str | None,
    lca_term: str | None,
    lca_gloss: str | None,
    min_quality: int = 0,
) -> PairAssessment:
    """Hard-filter a leaf pair / LCA, then score soft divergence axes.

    On reject, ``quality`` is 0.
    """
    structural = lca_structural_reject(lca_term, lca_gloss)
    if structural:
        return PairAssessment(reject=structural)

    if english_term_is_lca_gloss(lang_a, term_a, lca_gloss) or english_term_is_lca_gloss(
        lang_b, term_b, lca_gloss
    ):
        return PairAssessment(reject="english_term_is_lca_gloss")

    score = quality_score(
        lang_a=lang_a,
        lang_b=lang_b,
        term_a=term_a,
        term_b=term_b,
        gloss_a=gloss_a,
        gloss_b=gloss_b,
        lca_term=lca_term,
        lca_gloss=lca_gloss,
        min_quality=min_quality,
    )
    return PairAssessment(quality=score)

