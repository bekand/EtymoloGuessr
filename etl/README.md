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
| `etl/config.yaml` | Leaf languages, ancestor allowlist, reltypes, quality thresholds, source URLs |
| `etl/fixtures/` | Tiny committed graph + glosses for tests and local iteration |
| `data/raw/` | Downloaded parquet / JSONL, checksums, `manifest.json`, `NOTICE` (gitignored) |
| `data/derived/` | Filtered edges, gloss index (gitignored) |
| `data/puzzles/` | JSONL snapshots (gitignored) |
| `data/reports/` | `funnel.json`, `stats.json` (gitignored) |

Large dumps stay out of git. Pin URLs (and optional SHA-256) in `config.yaml`.

## Environment

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | Postgres DSN for `--db`, `load`, `disable`, `reset --puzzles`, `inspect --db`, `validate --db`, `doctor` |
| `ETL_DATA_DIR` | Override the `data/` root (tests use this) |
| `ETL_CONFIG` | Override `etl/config.yaml` |

The CLI never creates the `puzzles` table. Go owns migrations. ETL assumes the table already exists (`etl doctor` checks).

Expected columns: `id`, `enabled`, `leaf_a`, `leaf_b`, `prompt_graph`, `answer_graph`, `choices`, `correct_choice`, `quality_score`, `lang_pair`, `source`. Upserts key on `id`.

## Data sources and license

- [etymology-db](https://github.com/droher/etymology-db) (`etymology.parquet`, Dec 2023) — CC BY-SA 3.0
- [kaikki.org](https://kaikki.org/) / wiktextract dumps for glosses (the parquet has **no** meanings)

`refresh` copies a `NOTICE` into `data/raw/`. Derived puzzle data remains share-alike. Attribute Wiktionary + etymology-db in the game UI as well.

A full refresh is tens of minutes and hundreds of MB. The usual loop is `generate --stdout` / `--n 20` against already-built derived data. `generate` does **not** implicit-refresh (no surprise downloads).

## Pipeline stages

1. **Reduce graph** — keep leaf langs English / Spanish / Portuguese / German and the ancestor allowlist in config; keep `inherited_from`, `borrowed_from`, `derived_from`, `root`, `cognate_of`, `doublet_with`; drop null related terms, multiword junk, affixes.
2. **Index glosses** — first gloss per `(lang, term)`. Puzzles with no LCA gloss are skipped.
3. **Extract puzzles** — two modern leaves, connecting subgraph of 3-5 nodes, prefer cross-language via quality score, reject pairs where both leaves still mean the ancestor, 4-way multiple-choice from other LCA glosses.
4. **Ids** — SHA-256 of `(leaf_a, leaf_b, lca, gold edges)` so reruns upsert instead of duplicating. `--seed` controls sampling and choice shuffle.

Walks toward ancestors use `inherited_from` / `borrowed_from` / `derived_from` / `root` only.

## Quality score

Integer 0-5, stored on each puzzle. Start at 5, then:

| Penalty | Points |
|---|---|
| Same leaf language | -2 |
| Spanish–Portuguese pair | -1 |
| LCA is a modern leaf language (EN/ES/PT/DE) | -1 |
| High gloss overlap (either leaf still close to the LCA, or the two leaves to each other) | -1 |
| Low node count (3 nodes, the minimum) | -1 |

A pair of two different languages cannot fall below **1**, even with every other penalty. Same-language pairs can reach 0. Default `--min-quality` is `2` (config `generate.min_quality`).

## Commands

### `etl refresh`

Fetch etymology-db + gloss dumps into `data/raw/` if missing, verify checksums when `sha256` is set in config, write `NOTICE` + `manifest.json`, then rebuild `data/derived/` (filtered edges parquet + gloss index).

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
uv run etl generate --min-quality 3
uv run etl generate --dry-run                      # funnel only, no write
uv run etl generate --stdout                       # JSON array on stdout
uv run etl generate --jsonl path/to/puzzles.jsonl
uv run etl generate --db                           # upsert into Postgres
uv run etl generate -v --n 10                      # timed stage progress on stderr
```

Flags:

| Flag | Meaning |
|---|---|
| `--n N` | Max puzzles. Default from `config.yaml` (`generate.n`, currently 50). `0` = emit every survivor |
| `--seed` | Sampling and choice shuffle (default `generate.seed`) |
| `--lang-pair` | Repeatable filter, codes like `en-de` (sorted alphabetically) |
| `--min-quality` | Drop candidates below this integer score (default `generate.min_quality`, currently 2) |
| `--stdout` / `--jsonl PATH` / `--db` | Mutually exclusive sinks |
| `--dry-run` | Print counts / write `data/reports/funnel.json` only |
| `--verbose` / `-v` | Timed stage progress on stderr (load derived, build graph, candidates, emit, write). Also accepted as `etl -v generate …` |

If you omit every sink, output is `data/puzzles/puzzles.jsonl`. Funnel counts always go to stderr and `data/reports/funnel.json`.

With `--n > 0`, candidate search **early-exits** once enough quality survivors are found (and only walks leaf pairs that share an ancestor). Use `--n 0` for a full pass. Early exit can change which top-N puzzles you get versus an exhaustive quality sort over every pair.

Rejection reasons in the funnel include `no_gloss`, `too_big`, `too_small`, `same_meaning`, `no_lca`, `below_min_quality`, `early_exit`.

### `etl reset`

Regenerate from scratch. **Never** `DROP DATABASE`. Later, when users/scores exist, those tables must not be dropped either; this command only touches puzzle rows and `data/`.

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

Schema-check a puzzle set. Failures include: not exactly 4 choices, duplicate ids, graph not 3–5 nodes, leaves missing from the graph, gold edges that reference unknown node ids, distractors equal to the correct gloss, prompt graph leaking gold edges.

```bash
uv run etl validate
uv run etl validate path/to/puzzles.jsonl
uv run etl validate --db
```

Exit code `1` if any puzzle fails.

### `etl load PATH`

Validate a JSONL file and upsert it into Postgres without regenerating. Use for fixtures or a reviewed set someone else generated.

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

After Postgres and migrations exist:

```bash
uv run etl doctor
uv run etl generate --db --n 50 --seed 1
uv run etl inspect --db --random
uv run etl disable <id>          # if a row looks wrong
```

Reload everything from fixtures into the DB:

```bash
uv run etl reset --all --reload --fixtures
```

## Tests

```bash
uv run pytest
```

Tests copy fixtures into a temp `ETL_DATA_DIR` and exercise refresh, generate, doctor, inspect, validate, stats, and reset without downloading dumps.
