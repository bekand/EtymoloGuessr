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


def reduce_edges(df: pd.DataFrame, cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    cfg = cfg or load_config()
    langs = allowed_languages(cfg)
    reltypes = set(cfg["keep_reltypes"])
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
    log.info(
        "reduce_edges: in=%s drop_reltype=%s drop_junk=%s drop_lang=%s out=%s",
        before,
        dropped_rel,
        dropped_junk,
        dropped_lang,
        len(out),
    )
    return out.reset_index(drop=True)


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

_LEMMA_HOPS = 3


def is_grammatical_gloss(text: str | None) -> bool:
    """True when a gloss is a grammatical-form label rather than a meaning."""
    if not text:
        return False
    return bool(_FORM_GLOSS_RE.search(text.strip()))


def _is_inflection_sense(sense: dict[str, Any], parts: list[str]) -> bool:
    if sense.get("form_of"):
        return True
    tags = sense.get("tags") or []
    if isinstance(tags, list) and any(str(t).casefold() == "form-of" for t in tags):
        return True
    return bool(parts) and is_grammatical_gloss(parts[0])


def first_gloss(obj: dict[str, Any]) -> str | None:
    for sense in obj.get("senses") or []:
        parts = _sense_gloss_parts(sense)
        if not parts or _is_inflection_sense(sense, parts):
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
    s = re.sub(r"\s*\(.*$", "", s)
    s = s.rstrip(":").strip()
    return s or None


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
    word = str(obj.get("word") or "")
    for sense in obj.get("senses") or []:
        parts = _sense_gloss_parts(sense)
        if not _is_inflection_sense(sense, parts):
            continue
        lemma = _lemma_from_sense(sense, parts)
        if lemma and lemma != word:
            return lemma
    return None


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
        return term, gloss
    folded_hit = folded.get(f"{lang}\t{_fold_macrons(term)}")
    if folded_hit:
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


def iter_gloss_files(raw: Path | None = None) -> Iterable[Path]:
    raw = raw or raw_dir()
    yield from sorted(raw.glob("kaikki*.jsonl"))
    extra = raw / "glosses.jsonl"
    if extra.exists():
        yield extra


def index_gloss_objects(
    objects: Iterable[dict[str, Any]],
    langs: set[str] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Index lexical glosses, then inherit lemma senses onto form-only keys.

    Returns ``(gloss_index, lemma_index)``. ``lemma_index`` maps form-only
    ``lang\\tterm`` keys to the citation lemma whose gloss was inherited.
    """
    index: dict[str, str] = {}
    pending: dict[str, str] = {}
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
            index.setdefault(key, gloss)
            pending.pop(key, None)
            continue
        if key in index:
            continue
        lemma = _form_lemma(obj)
        if lemma:
            pending.setdefault(key, lemma)

    folded: dict[str, tuple[str, str]] = {}
    for key, gloss in index.items():
        lang, term = key.split("\t", 1)
        folded.setdefault(f"{lang}\t{_fold_macrons(term)}", (term, gloss))

    lemmas: dict[str, str] = {}
    for key, lemma in pending.items():
        if key in index:
            continue
        lang, term = key.split("\t", 1)
        resolved = _resolve_lemma_gloss(lang, lemma, index, pending, folded)
        if not resolved:
            continue
        canon, gloss = resolved
        index[key] = gloss
        if canon != term:
            lemmas[key] = canon
    return index, lemmas


def index_glosses(
    raw: Path | None = None, langs: set[str] | None = None
) -> tuple[dict[str, str], dict[str, str]]:
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

    index, lemmas = index_gloss_objects(_iter_objects(), langs=langs)
    log.info("gloss_index: unique=%s lemmas=%s", len(index), len(lemmas))
    return index, lemmas


def gloss_for(index: dict[str, str], lang: str, term: str) -> str | None:
    return index.get(f"{lang}\t{term}")


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


def derived_meta_path() -> Path:
    return derived_dir() / "meta.json"


def derived_ready() -> bool:
    return derived_edges_path().exists() and derived_gloss_path().exists()


def rebuild_derived(cfg: dict[str, Any] | None = None) -> None:
    cfg = cfg or load_config()
    dest = derived_dir()
    dest.mkdir(parents=True, exist_ok=True)
    df = reduce_edges(load_raw_edges(), cfg)
    df.to_parquet(derived_edges_path(), index=False)
    langs = allowed_languages(cfg)
    glosses, lemmas = index_glosses(langs=langs)
    derived_gloss_path().write_text(json.dumps(glosses, ensure_ascii=False) + "\n", encoding="utf-8")
    derived_lemma_path().write_text(json.dumps(lemmas, ensure_ascii=False) + "\n", encoding="utf-8")
    meta = {
        "n_edges": int(len(df)),
        "n_glosses": len(glosses),
        "n_lemmas": len(lemmas),
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
