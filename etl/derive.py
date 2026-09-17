from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from etl.paths import derived_dir, load_config, raw_dir

log = logging.getLogger(__name__)

EDGE_COLUMNS = ["term", "lang", "reltype", "related_term", "related_lang"]
MAX_TERM_LENGTH = 80


def is_junk_term(term: Any) -> bool:
    if term is None or (isinstance(term, float) and pd.isna(term)):
        return True
    s = str(term).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return True
    if s.startswith("-") or s.endswith("-"):
        return True
    if " " in s and not s.startswith("*"):
        return True
    if len(s) > MAX_TERM_LENGTH:
        return True
    if re.search(r"[\\/|]", s):
        return True
    return False


def allowed_languages(cfg: dict[str, Any]) -> set[str]:
    leaves = set(cfg["leaf_languages"].keys())
    ancestors = set(cfg.get("ancestor_languages") or [])
    return leaves | ancestors


def load_raw_edges(raw: Path | None = None) -> pd.DataFrame:
    raw = raw or raw_dir()
    parquet = raw / "etymology.parquet"
    jsonl = raw / "etymology.jsonl"
    if parquet.exists():
        df = pd.read_parquet(parquet)
    elif jsonl.exists():
        df = pd.read_json(jsonl, lines=True)
    else:
        raise SystemExit(
            f"no etymology dump in {raw} (expected etymology.parquet or etymology.jsonl). Run: etl refresh"
        )
    missing = [c for c in EDGE_COLUMNS if c not in df.columns]
    if missing:
        raise SystemExit(f"etymology dump missing columns: {missing}")
    return df[EDGE_COLUMNS]


def reduce_edges(
    df: pd.DataFrame,
    cfg: dict[str, Any] | None = None,
    parents: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    cfg = cfg or load_config()
    langs = allowed_languages(cfg)
    reltypes = set(cfg["keep_reltypes"])
    ancestor_reltypes = set(cfg.get("ancestor_reltypes") or [])
    out = df.copy()
    for col in EDGE_COLUMNS:
        out[col] = out[col].where(out[col].notna(), None)
    before = len(out)
    out = out[out["reltype"].isin(reltypes)]
    dropped_rel = before - len(out)
    mask_junk = out["term"].map(is_junk_term) | out["related_term"].map(is_junk_term)
    dropped_junk = int(mask_junk.sum())
    out = out.loc[~mask_junk]
    mask_lang = out["lang"].isin(langs) & out["related_lang"].isin(langs)
    dropped_lang = int((~mask_lang).sum())
    out = out.loc[mask_lang]
    out = out.drop_duplicates(subset=EDGE_COLUMNS)
    out, drop_align, align_fallback = _align_ancestor_edges(out, parents, ancestor_reltypes)
    log.info(
        "reduce_edges: in=%s drop_reltype=%s drop_junk=%s drop_lang=%s drop_etym_align=%s "
        "etym_align_fallback=%s out=%s",
        before,
        dropped_rel,
        dropped_junk,
        dropped_lang,
        drop_align,
        align_fallback,
        len(out),
    )
    return out.reset_index(drop=True)


_PARENT_TEMPLATE_NAMES = frozenset({"inh", "bor", "der", "root"})


def _template_arg(args: dict[str, Any], key: str) -> str:
    raw = args.get(key)
    if raw is None:
        try:
            raw = args.get(int(key))
        except ValueError:
            raw = None
    if raw is None:
        return ""
    return str(raw).strip()


def etymology_parent_terms(obj: dict[str, Any]) -> list[str]:
    """Related terms from the gloss object's ``inh`` / ``bor`` / ``der`` / ``root`` templates.

    Ignores nested ``etymon`` blobs. Parent term is template ``args["3"]``.
    """
    terms: list[str] = []
    seen: set[str] = set()
    for tmpl in obj.get("etymology_templates") or []:
        if not isinstance(tmpl, dict):
            continue
        if tmpl.get("name") not in _PARENT_TEMPLATE_NAMES:
            continue
        args = tmpl.get("args") or {}
        if not isinstance(args, dict):
            continue
        term = _template_arg(args, "3")
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def _align_ancestor_edges(
    df: pd.DataFrame,
    parents: dict[str, list[str]] | None,
    ancestor_reltypes: set[str],
) -> tuple[pd.DataFrame, int, int]:
    """Drop ancestor edges whose related_term is not in the winning-gloss allowlist.

    If filtering would remove every ancestor edge for a source term, keep the
    original ancestor edges for that term (template/dump spelling miss).
    Non-ancestor reltypes are never filtered.
    """
    if not parents or df.empty or not ancestor_reltypes:
        return df, 0, 0
    allow = {k: set(v) for k, v in parents.items() if v}
    if not allow:
        return df, 0, 0
    is_anc = df["reltype"].isin(ancestor_reltypes)
    if not bool(is_anc.any()):
        return df, 0, 0
    keys = df["lang"].astype(str) + "\t" + df["term"].astype(str)
    keep_idx: list[Any] = list(df.index[~is_anc])
    dropped = 0
    fallback = 0
    anc = df.loc[is_anc]
    grouped = anc.groupby(keys.loc[is_anc], sort=False)
    for key, grp in grouped:
        terms = allow.get(str(key))
        if not terms:
            keep_idx.extend(grp.index)
            continue
        hit = grp[grp["related_term"].isin(terms)]
        if len(hit):
            dropped += len(grp) - len(hit)
            keep_idx.extend(hit.index)
        else:
            fallback += 1
            keep_idx.extend(grp.index)
    return df.loc[keep_idx], dropped, fallback


def _sense_gloss_parts(sense: dict[str, Any]) -> list[str]:
    raw = sense.get("glosses") or sense.get("raw_glosses") or []
    parts: list[str] = []
    for item in raw:
        g = str(item).strip()
        if g:
            parts.append(g)
    return parts


# Grammatical-form labels, not lexical meanings. ``present`` / ``perfect`` require
# ``of`` so glosses like "present, a gift" stay lexical. ``masculine, male (of
# humans)`` does not match: it is not "masculine singular/plural/of …".
_FORM_GLOSS_RE = re.compile(
    r"(?ix)^(?:"
    r"inflection\s+of\b"
    r"|(?:first|second|third)-person\b"
    r"|(?:gerund|gerundive|supine|infinitive|imperative|subjunctive|indicative)\b"
    r"|(?:accusative|genitive|dative|ablative|nominative|vocative|locative)\b"
    r"|(?:present|perfect|imperfect|pluperfect|future|aorist|participle)\b.*\bof\b"
    r"|(?:feminine|masculine|neuter)\s+(?:singular|plural|of)\b"
    r"|(?:singular|plural)\s+of\b"
    r")"
)

# Wiktionary redirect stubs ("alternative form of X"), not lexical meanings.
# Anchored at start so "One of a number of alternative forms of the same gene…"
# stays lexical.
_REDIRECT_GLOSS_RE = re.compile(
    r"(?ix)^(?:"
    r"alternative\s+(?:form|spelling|capitalization|typography)"
    r"|(?:obsolete|archaic|dated|rare)\s+(?:form|spelling)"
    r"|misspelling|common\s+misspelling"
    r"|eye\s+dialect|pronunciation\s+spelling"
    r"|nonstandard\s+form"
    r"|synonym|abbreviation|initialism|acronym|clipping|ellipsis"
    r")\s+of\b"
)

# Wiktionary case-government / auxiliary labels, e.g. ``[with genitive]``,
# ``[of place] above``. Not chemistry/notation brackets like ``[α]_D``.
_CASE_QUALIFIER_RE = re.compile(
    r"(?i)^\["
    r"(?:"
    r"with(?:\s+the)?\s+(?:genitive|dative|accusative|ablative|nominative|vocative|locative)"
    r"|of\s+(?:place|time|person|persons)"
    r"|auxiliary\s+(?:haben|sein)"
    r")"
    r"[^\]]*\]\s*"
)

_INLINE_QUOTED_SENSE_RE = re.compile(r'[“"]([^”"]+)[”"]')

_LEMMA_HOPS = 3


def _strip_case_qualifier(text: str) -> str:
    s = text.strip()
    if not _CASE_QUALIFIER_RE.match(s):
        return s
    return _CASE_QUALIFIER_RE.sub("", s, count=1).strip()


def _drop_case_qualifiers(parts: list[str]) -> list[str]:
    out: list[str] = []
    for part in parts:
        rest = _strip_case_qualifier(part)
        if rest:
            out.append(rest)
    return out


def is_grammatical_gloss(text: str | None) -> bool:
    """True when a gloss is a grammatical-form label rather than a meaning."""
    if not text:
        return False
    s = text.strip()
    if _CASE_QUALIFIER_RE.match(s) and not _strip_case_qualifier(s):
        return True
    return bool(_FORM_GLOSS_RE.search(s))


def is_redirect_gloss(text: str | None) -> bool:
    """True when a gloss is a Wiktionary redirect stub, not a meaning."""
    if not text:
        return False
    return bool(_REDIRECT_GLOSS_RE.match(text.strip()))


def _is_inflection_sense(sense: dict[str, Any], parts: list[str]) -> bool:
    """True for grammatical form-of senses (not bare redirect stubs)."""
    if sense.get("form_of"):
        # form_of with a redirect gloss is still a redirect, not an inflection rewrite.
        if parts and is_redirect_gloss(parts[0]) and not is_grammatical_gloss(parts[0]):
            return False
        return True
    tags = sense.get("tags") or []
    if isinstance(tags, list) and any(str(t).casefold() == "form-of" for t in tags):
        if parts and is_redirect_gloss(parts[0]) and not is_grammatical_gloss(parts[0]):
            return False
        return True
    return bool(parts) and is_grammatical_gloss(parts[0])


def _is_redirect_sense(sense: dict[str, Any], parts: list[str]) -> bool:
    if not parts:
        return False
    if is_grammatical_gloss(parts[0]):
        return False
    return is_redirect_gloss(parts[0])


def _is_nonlexical_sense(sense: dict[str, Any], parts: list[str]) -> bool:
    return _is_inflection_sense(sense, parts) or _is_redirect_sense(sense, parts)


def first_gloss(obj: dict[str, Any]) -> str | None:
    for sense in obj.get("senses") or []:
        parts = _drop_case_qualifiers(_sense_gloss_parts(sense))
        if not parts or _is_nonlexical_sense(sense, parts):
            continue
        if parts[0].endswith(":") and len(parts) > 1:
            return " ".join(parts)
        return parts[0]
    return None


def _first_lemma_word(text: str) -> str | None:
    s = text.strip()
    if not s:
        return None
    s = re.split(r"\s+and\s+", s, maxsplit=1, flags=re.IGNORECASE)[0]
    s = s.split("/")[0]
    s = s.split(":")[0]
    s = re.sub(r"\s*\(.*$", "", s)
    s = s.rstrip(".").strip()
    return s or None


def _inline_redirect_sense(text: str) -> str | None:
    """Extract an embedded meaning from a redirect gloss when the target is missing.

    Handles ``… of lemma: sense`` and ``… of lemma (…, "sense")``.
    """
    s = text.strip()
    if ":" in s:
        after = s.split(":", 1)[1].strip().rstrip(".")
        if after and not is_redirect_gloss(after) and not is_grammatical_gloss(after):
            return after
    quoted = _INLINE_QUOTED_SENSE_RE.search(s)
    if quoted:
        sense = quoted.group(1).strip()
        if sense and not is_redirect_gloss(sense) and not is_grammatical_gloss(sense):
            return sense
    return None


def _lemma_from_sense(sense: dict[str, Any], parts: list[str]) -> str | None:
    for item in sense.get("form_of") or []:
        if isinstance(item, dict):
            word = str(item.get("word") or "").strip()
        else:
            word = str(item).strip()
        if word:
            return _first_lemma_word(word)
    if not parts:
        return None
    match = re.search(r"(?i)\bof\s+(.+)$", parts[0])
    if not match:
        return None
    return _first_lemma_word(match.group(1))


def _form_lemma(obj: dict[str, Any]) -> str | None:
    """Citation lemma for a grammatical form-only entry (lemma_index candidate)."""
    word = str(obj.get("word") or "")
    for sense in obj.get("senses") or []:
        parts = _sense_gloss_parts(sense)
        if not _is_inflection_sense(sense, parts):
            continue
        lemma = _lemma_from_sense(sense, parts)
        if lemma and lemma != word:
            return lemma
    return None


def _redirect_lemma(obj: dict[str, Any]) -> tuple[str | None, str | None]:
    """Citation lemma and optional inline sense for a redirect-only entry."""
    word = str(obj.get("word") or "")
    for sense in obj.get("senses") or []:
        parts = _sense_gloss_parts(sense)
        if not _is_redirect_sense(sense, parts):
            continue
        lemma = _lemma_from_sense(sense, parts)
        inline = _inline_redirect_sense(parts[0]) if parts else None
        if lemma and lemma != word:
            return lemma, inline
        if inline:
            return None, inline
    return None, None


def _fold_macrons(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _lookup_lexical(
    lang: str,
    term: str,
    index: dict[str, str],
    folded: dict[str, tuple[str, str]],
) -> tuple[str, str] | None:
    key = f"{lang}\t{term}"
    gloss = index.get(key)
    if gloss:
        # Skip unresolved redirect/grammatical stubs still sitting in an old index.
        if is_redirect_gloss(gloss) or is_grammatical_gloss(gloss):
            return None
        return term, gloss
    folded_hit = folded.get(f"{lang}\t{_fold_macrons(term)}")
    if folded_hit:
        _term, folded_gloss = folded_hit
        if is_redirect_gloss(folded_gloss) or is_grammatical_gloss(folded_gloss):
            return None
        return folded_hit
    return None


def _resolve_lemma_gloss(
    lang: str,
    lemma: str,
    index: dict[str, str],
    pending: dict[str, str],
    folded: dict[str, tuple[str, str]],
) -> tuple[str, str] | None:
    seen: set[str] = set()
    current = lemma
    for _ in range(_LEMMA_HOPS + 1):
        if current in seen:
            break
        seen.add(current)
        hit = _lookup_lexical(lang, current, index, folded)
        if hit:
            return hit
        nxt = pending.get(f"{lang}\t{current}")
        if not nxt or nxt == current:
            break
        current = nxt
    return None


def _unwrap_redirect_text(
    index: dict[str, str],
    lang: str,
    gloss: str,
    *,
    hops: int = _LEMMA_HOPS,
) -> str | None:
    """Follow ``alternative form of X`` (etc.) to a lexical gloss, or use inline sense."""
    seen: set[str] = set()
    current = gloss
    for _ in range(hops + 1):
        if current in seen:
            break
        seen.add(current)
        if not is_redirect_gloss(current):
            if is_grammatical_gloss(current):
                return None
            return current
        match = re.search(r"(?i)\bof\s+(.+)$", current)
        inline = _inline_redirect_sense(current)
        if not match:
            return inline
        lemma = _first_lemma_word(match.group(1))
        if not lemma:
            return inline
        hit = index.get(f"{lang}\t{lemma}")
        if not hit:
            return inline
        if is_redirect_gloss(hit) or is_grammatical_gloss(hit):
            current = hit
            continue
        return hit
    return None


def iter_gloss_files(raw: Path | None = None) -> Iterable[Path]:
    raw = raw or raw_dir()
    yield from sorted(raw.glob("kaikki*.jsonl"))
    extra = raw / "glosses.jsonl"
    if extra.exists():
        yield extra


def index_gloss_objects(
    objects: Iterable[dict[str, Any]],
    langs: set[str] | None = None,
) -> tuple[dict[str, str], dict[str, str], dict[str, list[str]]]:
    """Index lexical glosses, then inherit lemma senses onto form-only keys.

    Returns ``(gloss_index, lemma_index, etym_parents)``. ``lemma_index`` maps
    grammatical form-only ``lang\\tterm`` keys to the citation lemma whose gloss
    was inherited (not redirect stubs — those inherit meaning only).
    ``etym_parents`` maps ``lang\\tterm`` to related terms from the same kaikki
    object that supplied the stored gloss (``inh`` / ``bor`` / ``der`` /
    ``root``). Form-only keys that inherit a gloss do not copy the lemma's
    parent allowlist.
    """
    index: dict[str, str] = {}
    pending: dict[str, str] = {}
    pending_redirect: dict[str, str] = {}
    redirect_inline: dict[str, str] = {}
    parents: dict[str, list[str]] = {}
    for obj in objects:
        lang = obj.get("lang")
        word = obj.get("word")
        if not lang or not word:
            continue
        if langs is not None and lang not in langs:
            continue
        key = f"{lang}\t{word}"
        gloss = first_gloss(obj)
        if gloss:
            if key not in index:
                index[key] = gloss
                parent_terms = etymology_parent_terms(obj)
                if parent_terms:
                    parents[key] = parent_terms
            pending.pop(key, None)
            pending_redirect.pop(key, None)
            redirect_inline.pop(key, None)
            continue
        if key in index:
            continue
        lemma = _form_lemma(obj)
        if lemma:
            pending.setdefault(key, lemma)
            continue
        redir_lemma, inline = _redirect_lemma(obj)
        if redir_lemma:
            pending_redirect.setdefault(key, redir_lemma)
            if inline:
                redirect_inline.setdefault(key, inline)
        elif inline:
            index[key] = inline

    folded: dict[str, tuple[str, str]] = {}
    for key, gloss in index.items():
        lang, term = key.split("\t", 1)
        folded.setdefault(f"{lang}\t{_fold_macrons(term)}", (term, gloss))

    # Redirect pending can chain through other redirects and grammatical forms.
    all_pending = {**pending, **pending_redirect}

    lemmas: dict[str, str] = {}
    for key, lemma in pending.items():
        if key in index:
            continue
        lang, term = key.split("\t", 1)
        resolved = _resolve_lemma_gloss(lang, lemma, index, all_pending, folded)
        if not resolved:
            continue
        canon, gloss = resolved
        index[key] = gloss
        if canon != term:
            lemmas[key] = canon

    for key, lemma in pending_redirect.items():
        if key in index:
            continue
        lang, term = key.split("\t", 1)
        resolved = _resolve_lemma_gloss(lang, lemma, index, all_pending, folded)
        if resolved:
            _canon, gloss = resolved
            index[key] = gloss
            # Intentionally omit from lemma_index: keep surface form in the gold graph.
            continue
        inline = redirect_inline.get(key)
        if inline:
            index[key] = inline

    return index, lemmas, parents


def index_glosses(
    raw: Path | None = None, langs: set[str] | None = None
) -> tuple[dict[str, str], dict[str, str], dict[str, list[str]]]:
    def _iter_objects() -> Iterable[dict[str, Any]]:
        n_lines = 0
        for path in iter_gloss_files(raw):
            log.info("indexing glosses %s", path.name)
            with path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    n_lines += 1
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        log.info("gloss_index: lines=%s", n_lines)

    index, lemmas, parents = index_gloss_objects(_iter_objects(), langs=langs)
    log.info(
        "gloss_index: unique=%s lemmas=%s etym_parents=%s",
        len(index),
        len(lemmas),
        len(parents),
    )
    return index, lemmas, parents


def gloss_for(index: dict[str, str], lang: str, term: str) -> str | None:
    """Look up a lexical gloss, unwrapping leftover redirect stubs from old indexes."""
    gloss = index.get(f"{lang}\t{term}")
    if not gloss:
        return None
    if is_redirect_gloss(gloss):
        return _unwrap_redirect_text(index, lang, gloss)
    if is_grammatical_gloss(gloss):
        return None
    return gloss


def lemma_for(lemmas: dict[str, str], lang: str, term: str) -> str | None:
    return lemmas.get(f"{lang}\t{term}")


def canonical_lemma(lemmas: dict[str, str], lang: str, term: str) -> str:
    """Follow lemma_index hops to the citation form, or return ``term``."""
    seen: set[str] = set()
    current = term
    while True:
        key = f"{lang}\t{current}"
        if key in seen:
            return current
        nxt = lemmas.get(key)
        if not nxt or nxt == current:
            return current
        seen.add(key)
        current = nxt


def derived_edges_path() -> Path:
    return derived_dir() / "edges.parquet"


def derived_gloss_path() -> Path:
    return derived_dir() / "gloss_index.json"


def derived_lemma_path() -> Path:
    return derived_dir() / "lemma_index.json"


def derived_etym_parents_path() -> Path:
    return derived_dir() / "etym_parents.json"


def derived_meta_path() -> Path:
    return derived_dir() / "meta.json"


def derived_ready() -> bool:
    return derived_edges_path().exists() and derived_gloss_path().exists()


def rebuild_derived(cfg: dict[str, Any] | None = None) -> None:
    cfg = cfg or load_config()
    dest = derived_dir()
    dest.mkdir(parents=True, exist_ok=True)
    langs = allowed_languages(cfg)
    glosses, lemmas, parents = index_glosses(langs=langs)
    df = reduce_edges(load_raw_edges(), cfg, parents=parents)
    df.to_parquet(derived_edges_path(), index=False)
    derived_gloss_path().write_text(json.dumps(glosses, ensure_ascii=False) + "\n", encoding="utf-8")
    derived_lemma_path().write_text(json.dumps(lemmas, ensure_ascii=False) + "\n", encoding="utf-8")
    derived_etym_parents_path().write_text(
        json.dumps(parents, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    meta = {
        "n_edges": int(len(df)),
        "n_glosses": len(glosses),
        "n_lemmas": len(lemmas),
        "n_etym_parents": len(parents),
        "reltypes": df["reltype"].value_counts().to_dict() if len(df) else {},
        "langs": df["lang"].value_counts().to_dict() if len(df) else {},
    }
    derived_meta_path().write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    log.info("wrote derived artifacts to %s", dest)


def load_derived_edges() -> pd.DataFrame:
    path = derived_edges_path()
    if not path.exists():
        raise SystemExit("derived edges missing. Run: etl refresh")
    return pd.read_parquet(path)


def load_gloss_index() -> dict[str, str]:
    path = derived_gloss_path()
    if not path.exists():
        raise SystemExit("derived gloss index missing. Run: etl refresh")
    return json.loads(path.read_text(encoding="utf-8"))


def load_lemma_index() -> dict[str, str]:
    path = derived_lemma_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_etym_parents() -> dict[str, list[str]]:
    path = derived_etym_parents_path()
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): [str(t) for t in v] for k, v in raw.items()}
