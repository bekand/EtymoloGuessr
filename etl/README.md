# Etymology ETL

Python Typer CLI that turns Wiktionary-derived etymology dumps into pregenerated puzzles. The game API never walks the live graph: `refresh` builds staged artifacts, `generate` emits puzzle rows, and the Go service only reads those rows.

Install from the repo root:

```bash
uv sync --extra dev
uv run etl --help
```

`--verbose` / `-v` on the root command turns on debug logs (written to stderr).

## Layout

| Path | Role |
|---|---|
| `etl/cli.py` | Typer entrypoint (`uv run etl`) |
| `etl/core/` | Shared models, paths, ids, logging |
| `etl/pipeline/` | `refresh`, `gloss`, `reduce`, `derive`, `extract`, `quality`, `emit`, `generate`, `validate` — [step diagrams](pipeline/README.md) |
| `etl/store/` | JSONL and Postgres |
| `etl/commands/` | `doctor`, `stats`, `inspect`, `reset` helpers |
| `etl/config.yaml` | Leaf languages, ancestor allowlist, reltypes, quality thresholds, source URLs, local `database_url` |
| `etl/fixtures/` | Tiny committed graph + glosses for tests and local iteration |
| `etl/tests/` | Pytest: pipeline units, CLI fixture flow, optional Postgres |
| `data/raw/` | Downloaded parquet / JSONL, checksums, `manifest.json`, `NOTICE` (gitignored) |
| `data/derived/` | Filtered edges, gloss index, lemma index (gitignored) |
| `data/puzzles/` | JSONL snapshots (gitignored) |
| `data/reports/` | `funnel.json`, `stats.json` (gitignored) |

Large dumps stay out of git. Pin URLs (and optional SHA-256) in `config.yaml`.

## Environment

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | Optional override of `config.yaml` `database_url` (Compose DSN is the committed default) |
| `ETL_DATA_DIR` | Override the `data/` root (tests use this) |
| `ETL_CONFIG` | Override `etl/config.yaml` |

Postgres commands (`--db`, `load`, `disable`, `reset --puzzles`, `inspect --db`, `validate --db`, `doctor`) use `DATABASE_URL` if set, otherwise `database_url` in `etl/config.yaml`.

The CLI never creates the `puzzles` table. The Go API applies migrations on startup (`AUTO_MIGRATE=true`). ETL assumes the table already exists (`etl doctor` checks).

Expected columns: `id`, `enabled`, `leaf_a`, `leaf_b`, `answer_graph`, `choices`, `correct_choice`, `quality_score`, `lang_pair`, `source`. Upserts key on `id`.

Canonical gold is **`answer_graph` only**. The player prompt is derived as `{nodes: answer_graph.nodes, edges: []}` (`etl.core.models.prompt_graph_from_answer` / `Puzzle.prompt_graph`). JSONL and Postgres store only `answer_graph` — no `prompt_graph` field or column. The API derives mode-specific prompts at serve time: Hard keeps node glosses and drops edges; Medium exposes opaque leaf tokens for a four-puzzle set. Answer-graph nodes include a gloss whenever the index has one (leaves, LCA, and intermediates).

| Surface | Behavior |
|---|---|
| JSONL / `to_dict()` | Omits `prompt_graph` |
| Load / `from_dict()` | Requires `answer_graph`; rejects payloads that still include `prompt_graph` |
| Postgres upsert | Writes `answer_graph` only |
| Validate | Checks `answer_graph` structure |
| Go API | `GET /puzzles/random` builds prompts from gold; never sends edges / `correct_choice` until `POST /puzzles/{id}/solve` |

## Data sources and license

- [etymology-db](https://github.com/droher/etymology-db) (`etymology.parquet`, Dec 2023) — CC BY-SA 3.0
- [kaikki.org](https://kaikki.org/) / wiktextract dumps for glosses (the parquet has **no** meanings)

`refresh` copies a `NOTICE` into `data/raw/`. Derived puzzle data remains share-alike. Attribute Wiktionary + etymology-db in the game UI as well.

A full refresh is tens of minutes and hundreds of MB. The usual loop is `generate --stdout` / `--n 20` against already-built derived data. `generate` does **not** implicit-refresh (no surprise downloads).

## Pipeline stages

Step-by-step diagrams: [`etl/pipeline/README.md`](pipeline/README.md).


1. **Reduce graph** — keep leaf langs English / Spanish / Portuguese / German and the ancestor allowlist in config; keep `inherited_from`, `borrowed_from`, `derived_from`, `root`, `cognate_of`, `doublet_with`; drop null related terms, multiword junk, affixes. Drop **cross-term leaf→leaf** ancestor hops (`hipoxia`→`oxygen`) but keep same-term loans (`panel`→`panel`). Align ancestor edges to the winning-gloss parent allowlist; Latin-family nodes with the same macron-folded spelling share reachability (`Late Latin:apostrŏphus` via `Latin:apostrophus`).
2. **Index glosses** — first *lexical* gloss per `(lang, term)` (skip `form_of` / grammatical-form senses and Wiktionary redirect stubs like `alternative form of …` / `synonym of …`; strip Wiktionary case-government labels like `[with genitive]`). Form-only grammatical entries inherit the citation lemma’s gloss and are recorded in `lemma_index.json` (so LCAs can be rewritten to that lemma). Redirect-only entries inherit the target’s meaning **without** a `lemma_index` entry (surface spelling stays in the gold graph). Puzzles with no LCA gloss are skipped (`no_gloss`).
3. **Extract puzzles** — two modern leaves and their closest connecting subgraph / LCA (at most 9 nodes; `too_big` otherwise), prefer cross-language via quality score, rewrite form-only LCAs to the citation lemma (`Latin:addere` → `Latin:addō`), unify ancestor nodes that share a gloss (same language with different spelling, or Latin-family langs with the same macron-folded spelling—prefer Classical Latin), then hard-filter in [`etl/pipeline/generate.py`](pipeline/generate.py) (`assess_pair`: short/unglossed/inflection LCA, English term≡LCA gloss) and soft-score via [`etl/pipeline/quality.py`](pipeline/quality.py) (`quality_score` cheap→expensive with early exit vs `min_quality`), 4-way multiple-choice from other LCA glosses.
4. **Ids** — SHA-256 of `(leaf_a, leaf_b, lca, gold edges)` so `etl load` upserts instead of duplicating. `generate --db` truncates first, then upserts. `--seed` shuffles English/non-English emit buckets (pair selection) and multiple-choice options.

Walks toward ancestors use `inherited_from` / `borrowed_from` / `derived_from` / `root` only.

## Quality score

Integer 0-5, stored on each puzzle. Start at 5; −1 for each missed divergence axis. Axes are evaluated **cheap → expensive** and may **early-exit** once the running score cannot meet `--min-quality` (so a discarded candidate’s stored lower bound may omit later meaning checks):

| Order | Miss | −1 when |
|---|---|---|
| 1 | Same language | Both leaves share a language |
| 2 | Spelling vs LCA | Either leaf term equals the LCA term after `normalize_label` |
| 3 | Spelling vs each other | Leaf terms equal after normalize, or both length ≥ 3 with the same 3-char prefix |
| 4 | Meaning vs each other | Leaf glosses share a **lemmatized** content token |
| 5 | Meaning vs LCA | Either leaf **gloss** shares a **lemmatized** content token with the LCA gloss (English glosses; not leaf terms) |

Meaning checks use `simplemma` English lemmas (`dogs` ↔ `dog`). Spelling axes stay orthographic (no lemmatization).

Default `--min-quality` is config `generate.min_quality` (currently 4), so a puzzle may miss at most one axis.

### Leaf filters and batch diversity

- **Proper nouns** — English / Spanish / Portuguese leaves whose term starts with an uppercase letter are skipped (`proper_noun_leaf`). German is exempt (common nouns are capitalized).
- **English term is LCA gloss** — when an English leaf’s term matches the LCA gloss’s **first** content token after dropping articles/function words (`gift` vs `a gift`, `tunic` vs `tunic, robe`), the pair is rejected (`english_term_is_lca_gloss`). Non-English leaves are not checked this way.
- **Short / unglossed terms** — leaf or LCA headwords shorter than 3 characters are skipped (`term_too_short`); missing LCA gloss uses existing `no_gloss`; missing leaf gloss uses `no_gloss_leaf`.
- **Form-only LCA** — if the closest ancestor is only a grammatical form (infinitive, supine, inflected case, …) and Wiktionary points at a citation lemma, the gold node is replaced by that lemma and the multiple-choice answer uses the lemma’s meaning. Homographs with a real lexical sense (Latin *factum* “deed”) are left alone. Glosses that still look like `accusative … of …` or `[with genitive]` are rejected (`inflection_lca`). Redirect stubs (`alternative form of …`, `synonym of …`, …) inherit the target lemma’s meaning at index/lookup time but **do not** rewrite the gold node spelling (Old French *amirail* stays *amirail*). Unresolved redirects are dropped via `no_gloss` / `no_gloss_leaf` and never used as distractors.
- **Hard rejects** — `term_too_short`, `no_gloss`, `inflection_lca`, `english_term_is_lca_gloss`. Divergence (meaning, spelling, same language) is scored, not hard-rejected.
- **Modern-language ancestors** — intermediate (non-leaf) nodes in English / Spanish / Portuguese / German are rejected (`modern_lang_ancestor`); gold paths must go through historical ancestors only.
- **Nonlexical ancestor glosses** — any ancestor whose gloss is still grammatical (`personal pronoun`, `… case`, …) or an unresolved redirect stub (including `diminutive of …`) is rejected (`nonlexical_ancestor` / `inflection_lca`).
- **Unify same-gloss ancestors** — before emit, collapse duplicate ancestor nodes that share an exact gloss: (1) same language with different spelling (`Latin:planēta` / `Latin:planeta`), or (2) Latin-family langs with the same macron-folded spelling (`Latin:bursa` / `Late Latin:bursa`). Prefer the LCA if present, else Classical `Latin`, else the diacritic form. Edges are remapped; self-loops dropped.
- **Leaf reuse** — within one `generate` batch, each `(lang, term)` may appear as a leaf in at most one emitted puzzle (`leaf_reuse`), so `--n 10` does not repeat the same word ten times.
- **English vs non-English emit** — after quality filter, candidates are split into English-involving vs other pairs, each bucket is seed-shuffled, then water-filled so `de-en` A-words do not lock shared leaves before `de-es` / `es-pt` / … Extraction also shuffles leaves within each ancestor group and (for finite `--n`) keeps walking until both buckets have headroom.
- **Distractors** — multiple-choice options come from other candidates’ LCA glosses. If fewer than `n_choices - 1` distinct real glosses are available, the candidate is rejected (`insufficient_distractors`); placeholders are never emitted.

## Commands

### `etl refresh`

Fetch etymology-db + gloss dumps into `data/raw/` if missing, verify checksums when `sha256` is set in config, write `NOTICE` + `manifest.json`, then rebuild `data/derived/` (filtered edges parquet + gloss index + lemma index).

Does **not** wipe puzzle rows in Postgres.

```bash
uv run etl refresh
uv run etl refresh --force              # re-download even if files exist
uv run etl refresh --skip-derived       # download only
uv run etl refresh --fixtures           # copy etl/fixtures into data/raw, then derive
```

`--fixtures` is the local/CI path: no network, tiny graph, enough puzzles to exercise generate / inspect / validate.

### `etl generate`

Read derived artifacts. Errors if they are missing (`run etl refresh`). Does not download.

```bash
uv run etl generate
uv run etl generate --n 20 --seed 1
uv run etl generate --n 0                          # all that pass filters
uv run etl generate --lang-pair en-de --lang-pair en-es
uv run etl generate --min-quality 4
uv run etl generate --dry-run                      # funnel only, no write
uv run etl generate --stdout                       # JSON array on stdout
uv run etl generate --jsonl path/to/puzzles.jsonl
uv run etl generate --db                           # replace Postgres puzzles (truncates scores too)
uv run etl generate -v --n 10                      # timed stage progress on stderr
```

Flags:

| Flag | Meaning |
|---|---|
| `--n N` | Max puzzles. Default from `config.yaml` (`generate.n`, currently 0). `0` = emit every survivor |
| `--seed` | Shuffle English/non-English emit buckets (pair selection) and MC choices (default `generate.seed`) |
| `--lang-pair` | Repeatable filter, codes like `en-de` (sorted alphabetically) |
| `--min-quality` | Drop candidates below this integer score (default `generate.min_quality`, currently 4) |
| `--stdout` / `--jsonl PATH` / `--db` | Mutually exclusive sinks |
| `--dry-run` | Print counts / write `data/reports/funnel.json` only |
| `--verbose` / `-v` | Timed stage progress on stderr (load derived, build graph, candidates, emit, write). Also accepted as `etl -v generate …` |

If you omit every sink, output is `data/puzzles/puzzles.jsonl`. Funnel counts always go to stderr and `data/reports/funnel.json`.

The Railway API embeds `backend/internal/catalog/puzzles.jsonl`. After a full generate, copy the snapshot there and redeploy the API (do not run ETL in the cloud):

```bash
cp data/puzzles/puzzles.jsonl backend/internal/catalog/puzzles.jsonl
```

**JSONL and Postgres are separate sinks.** `generate` always walks `data/derived/` and writes to exactly one of them (or stdout). It never reads an existing puzzle file.

| You want | Command |
|---|---|
| New JSONL (overwrite file; DB unchanged) | `etl generate` or `etl generate --jsonl PATH` |
| Replace Postgres puzzles (file unchanged; derived walked again; also truncates scores) | `etl generate --db` |
| File you already have → Postgres (upsert, no truncate) | `etl load PATH` (no generate) |
| Both a new file and DB | `etl generate --jsonl PATH` then `etl load PATH` |

`--db` truncates `puzzles` and `scores` (FK requires both), then upserts the new batch. It does not reuse `puzzles.jsonl` on purpose: that file may be a reviewed subset, a different `--n`/`--seed`, or stale vs derived. `load` is the path that trusts the file and merges. `generate --db` is the path that trusts the graph and **replaces** table contents so rejected leftovers (for example old "inflection of ..." LCAs) disappear.

With `--n > 0`, candidate search **early-exits** once enough quality survivors are found (and only walks leaf pairs that share an ancestor). Use `--n 0` for a full pass. Early exit can change which top-N puzzles you get versus an exhaustive quality sort over every pair.

Rejection reasons in the funnel include `no_gloss`, `term_too_short`, `inflection_lca`, `english_term_is_lca_gloss`, `nonlexical_ancestor`, `modern_lang_ancestor`, `too_big`, `no_lca`, `proper_noun_leaf`, `below_min_quality`, `leaf_reuse`, `insufficient_distractors`, `early_exit`.

### `etl reset`

Regenerate from scratch. **Never** `DROP DATABASE` or drop the `users` / `scores` tables. `--puzzles` truncates puzzle rows and score rows (the FK from `scores` to `puzzles` blocks truncating puzzles alone, even when scores is empty). User rows are left alone.

```bash
uv run etl reset                    # default: truncate puzzles table + delete data/puzzles
uv run etl reset --puzzles
uv run etl reset --derived          # delete data/derived and reports
uv run etl reset --raw              # delete downloads
uv run etl reset --all              # raw + derived + puzzles
uv run etl reset --all --reload     # then refresh + generate --db
uv run etl reset --reload --fixtures
```

`--reload` always force-refreshes, generates, upserts to Postgres, and writes the default JSONL. Combine with `--fixtures` to skip the full dump download. If Postgres is unreachable during `--puzzles`, the DB truncate is skipped and a warning is printed.

### `etl doctor`

Health check. Prints a short summary plus a JSON report.

Checks:

- raw dumps present (parquet **or** fixture `etymology.jsonl`) and gloss files
- checksums when configured
- derived edges + gloss index present
- Postgres reachable (`DATABASE_URL`) and whether `public.puzzles` exists
- bytes used under `data/` and a full-refresh size estimate from config

Exit code `1` if raw or derived is missing. A missing database does not fail the process (v1 can generate JSONL without Postgres).

```bash
uv run etl doctor
```

### `etl stats`

Edge counts by language and reltype, puzzle counts by `lang_pair`, and the last generation funnel.

```bash
uv run etl stats
uv run etl stats --jsonl path/to/puzzles.jsonl
```

Writes `data/reports/stats.json` and prints JSON to stdout.

### `etl inspect`

Print one puzzle as readable text: leaves, glosses, choices (correct marked), gold edges, nodes. Use this before the UI exists.

```bash
uv run etl inspect                          # random from default JSONL
uv run etl inspect --random
uv run etl inspect --lang-pair de-en
uv run etl inspect <id>
uv run etl inspect --jsonl path/to/puzzles.jsonl <id>
uv run etl inspect --db --random
uv run etl inspect --db --lang-pair en-de
uv run etl inspect --db <id>
```

### `etl validate`

Schema-check a puzzle set. Failures include: not exactly 4 choices, duplicate ids, more than 9 nodes, leaves missing from the graph, gold edges that reference unknown node ids, distractors equal to the correct gloss. Payloads must not include a stored `prompt_graph` (derive from `answer_graph` instead).

```bash
uv run etl validate
uv run etl validate path/to/puzzles.jsonl
uv run etl validate --db
```

Exit code `1` if any puzzle fails.

### `etl load PATH`

Validate a JSONL file and upsert it into Postgres **without** walking the graph, truncating, or changing the file. This is how you reuse an existing `puzzles.jsonl` (or a snapshot someone else generated). `etl generate --db` instead replaces the puzzles table from a fresh graph walk.

```bash
uv run etl load data/puzzles/puzzles.jsonl
```

Requires `DATABASE_URL` and a migrated `puzzles` table.

### `etl disable ID`

Set `enabled=false` after a bad eyeball. The API should skip disabled rows.

```bash
uv run etl disable <puzzle-id>
```

## Typical loops

Local, no Postgres, fixture graph:

```bash
uv run etl refresh --fixtures
uv run etl generate --n 0 --stdout
uv run etl inspect --random
uv run etl validate
```

After Postgres exists (API applies migrations on startup):

```bash
docker compose up db -d
# ETL reads database_url from etl/config.yaml (override with DATABASE_URL if needed)
(cd backend && DATABASE_URL=postgres://etymologuessr:etymologuessr@localhost:5432/etymologuessr?sslmode=disable go run ./cmd/api)
uv run etl doctor
# already have puzzles.jsonl? load it — do not generate --db (that re-walks the graph and replaces DB rows)
uv run etl load data/puzzles/puzzles.jsonl
# or extract again from derived into Postgres only (truncates puzzles + scores first):
# uv run etl generate --db --n 50 --seed 1
uv run etl inspect --db --random
uv run etl disable <id>          # if a row looks wrong
```

Reload everything from fixtures into the DB:

```bash
uv run etl reset --all --reload --fixtures
```

## Tests

From the repo root:

```bash
uv run pytest
```

Offline tests live in `etl/tests/` (a temp `ETL_DATA_DIR`, no dump download). Postgres cases are marked `integration` and skip unless `TEST_DATABASE_URL` is set (see the root README).
