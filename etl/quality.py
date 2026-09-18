"""Hard rejects and quality scoring for puzzle candidates.

Kept separate from graph walking in ``etl.generate`` so filter logic can change
without touching LCA selection / emit buckets.
"""

from __future__ import annotations

from dataclasses import dataclass

from etl.derive import is_grammatical_gloss

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
MIN_TERM_LENGTH = 3


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


def normalize_label(text: str | None) -> str:
    """Casefold a term or gloss for identity checks; strip a reconstruction *."""
    if not text:
        return ""
    s = text.strip().casefold()
    if s.startswith("*"):
        s = s[1:].lstrip()
    return s


def content_tokens(text: str | None, *, head_only: bool = False) -> set[str]:
    """Content tokens after normalize_label; optionally only the first token."""
    tokens = set()
    for word in _iter_content_tokens(normalize_label(text)):
        tokens.add(word)
        if head_only:
            break
    return tokens


def meaning_overlap(a: str | None, b: str | None, *, head_only: bool = False) -> float:
    """Jaccard of content tokens (singletons when head_only). Empty side -> 0.0."""
    ta, tb = content_tokens(a, head_only=head_only), content_tokens(b, head_only=head_only)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def shares_meaning(a: str | None, b: str | None, *, head_only: bool = False) -> bool:
    """True when two labels share any content token (first token only if head_only)."""
    return meaning_overlap(a, b, head_only=head_only) > 0


def term_too_short(term: str | None) -> bool:
    """True when a headword is missing or shorter than MIN_TERM_LENGTH."""
    if not term:
        return True
    return len(term.strip()) < MIN_TERM_LENGTH


def similar_spelling(a: str | None, b: str | None) -> bool:
    """Equal after normalize, or both length >= 3 with the same 3-char prefix."""
    na, nb = normalize_label(a), normalize_label(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return len(na) >= 3 and len(nb) >= 3 and na[:3] == nb[:3]


def lca_structural_reject(lca_term: str | None, lca_gloss: str | None) -> str | None:
    """Funnel reason when the chosen LCA is unusable, or None to continue."""
    if term_too_short(lca_term):
        return "term_too_short"
    if not lca_gloss:
        return "no_gloss"
    if is_grammatical_gloss(lca_gloss):
        return "inflection_lca"
    return None


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
) -> int:
    """Integer 0-5. Start at 5; −1 for each missed divergence axis."""
    score = 5
    if shares_meaning(gloss_a, lca_gloss) or shares_meaning(gloss_b, lca_gloss):
        score -= 1
    na, nb, nl = normalize_label(term_a), normalize_label(term_b), normalize_label(lca_term)
    if na == nl or nb == nl:
        score -= 1
    if similar_spelling(term_a, term_b):
        score -= 1
    if shares_meaning(gloss_a, gloss_b):
        score -= 1
    if lang_a == lang_b:
        score -= 1
    return max(0, score)


@dataclass(frozen=True)
class PairAssessment:
    """Outcome of hard filters + quality scoring for one leaf pair / LCA."""

    reject: str | None = None
    quality: int = 0


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
) -> PairAssessment:
    """Run structural LCA checks, then the five-axis quality score.

    On reject, ``quality`` is 0.
    """
    structural = lca_structural_reject(lca_term, lca_gloss)
    if structural:
        return PairAssessment(reject=structural)

    score = quality_score(
        lang_a=lang_a,
        lang_b=lang_b,
        term_a=term_a,
        term_b=term_b,
        gloss_a=gloss_a,
        gloss_b=gloss_b,
        lca_term=lca_term,
        lca_gloss=lca_gloss,
    )
    return PairAssessment(quality=score)
