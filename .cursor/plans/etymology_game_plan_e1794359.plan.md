---
name: Etymology game plan
overview: "Greenfield etymology guessing game: Python ETL, Go API + Postgres, and a React UI on a paper/ink design system (typewriter type, post-it choices, card graphs)."
todos:
  - id: etl-cli
    content: "Python Typer CLI: refresh, generate (--n, stdout/jsonl/db), reset, doctor, stats, inspect, validate, load, disable"
    status: completed
  - id: etl-reduce
    content: Filter languages/reltypes, persist cleaned graph + gloss index as reusable artifacts
    status: completed
  - id: etl-puzzles
    content: Extract 3–5 node LCA puzzles, divergence filter, MC distractors, hashed ids, rejection log
    status: completed
  - id: db-api
    content: Postgres puzzle schema + Go API GET random / POST solve (hide gold until submit)
    status: pending
  - id: design-system
    content: Paper/ink tokens + primitive UI (Sheet, IndexCard, PostIt, InkButton, type) before game screens
    status: pending
  - id: frontend-easy
    content: "React easy mode: two words, MC, React Flow reveal"
    status: pending
  - id: frontend-hard
    content: "React Flow hard mode: place 1–3 ancestors, draw edges, score edge-set match"
    status: pending
  - id: compose
    content: Docker Compose for Postgres + API + frontend; CC BY-SA attribution in UI
    status: pending
isProject: false
---

# Etymology guessing game (v1)

Greenfield project (workspace is empty). Wiktionary-derived data is noisy and **has no meanings**, so the pipeline must join glosses from a second source and **prefer semantic-shift pairs** so multiple-choice is not trivial (EN *father* / DE *Vater* both mean “father”).

## Product (v1)

**Easy:** two modern words (from EN / ES / PT / DE) → pick the common ancestor’s meaning from 4 choices → on success, show a read-only etymology graph.

**Hard:** same puzzle family, 3–5 nodes. Leaves are placed; the player drag-and-drops ancestor node(s) and draws edges (React Flow). No inventing extra nodes; no relation-type labels on edges in v1. Score by comparing the submitted edge set to the gold graph (exact match to win; optional later: precision/recall partial credit).

**Out of scope for v1:** accounts, scoring persistence, leaderboards (schema can leave room). Daily challenge / explore-the-full-graph can wait.

**License:** etymology-db is [CC BY-SA 3.0](https://github.com/droher/etymology-db). Attribute Wiktionary + etymology-db in the UI and keep derived puzzle data share-alike.

## Why not query the live etymology graph at request time

Pregenerate puzzles. Serving becomes “pick a row, hide the answer, check a submission.” The graph walk, LCA search, gloss join, and distractor generation are slow, messy, and should be inspectable offline.

```mermaid
flowchart LR
  refresh[etl refresh]
  raw[data/raw]
  graph[data/derived graph plus glosses]
  gen[etl generate]
  out[stdout or JSONL]
  pg[(Postgres puzzles)]
  api[Go API]
  ui[React]
  refresh --> raw
  raw --> graph
  graph --> gen
  gen --> out
  gen --> pg
  pg --> api
  api --> ui
```



## Data pipeline (Python CLI)

One Typer (or Click) app, e.g. `uv run etl …`, with **staged artifacts** so generate does not re-download or rebuild the 4M-edge graph every time. Config in `etl/config.yaml` (leaf languages, ancestor allowlist, reltypes, quality thresholds). `DATABASE_URL` from env. Large dumps stay in `data/` and are **gitignored**; pin source URLs + checksums in config.

Source: [droher/etymology-db](https://github.com/droher/etymology-db) (`etymology.parquet`, Dec 2023). Edges: `term` / `lang` → `reltype` → `related_term` / `related_lang`. Glosses are **not** in that file — join [kaikki.org](https://kaikki.org/) / wiktextract dumps for the languages we keep.

### Layout

- `data/raw/` — parquet, gloss JSONL, checksums, `manifest.json` (url, date, hash)
- `data/derived/` — filtered edges, graph, gloss index keyed by `(lang, term)`
- `data/puzzles/` — optional JSONL snapshots
- `data/reports/` — rejection funnel, stats
- `etl/fixtures/` — tiny committed slice for tests (not the full dump)

### Stages (not one mega-script)

1. **Reduce graph** — keep leaf langs EN/ES/PT/DE (Wiktionary names); keep ancestor/path langs (Latin, OE, OHG, PGmc, PIE, Old French, Old Norse, Arabic, …) in config; keep `inherited_from`, `borrowed_from`, `derived_from`, `root`, `cognate_of`, `doublet_with`; drop null related terms, junk MWEs, affix/compound/group noise.
2. **Index glosses** — first gloss per `(lang, term)`; skip puzzles with no LCA gloss.
3. **Extract puzzles** — pairs of modern leaves with a short connecting subgraph / LCA; **3–5 nodes**; prefer cross-language; down-rank ES–PT clones; divergence filter (leaf/LCA gloss overlap); 4-way MC distractors from other LCAs.
4. **Ids** — content hash of `(leaf_a, leaf_b, lca, graph-edges)` so reruns upsert instead of duplicating. `--seed` for sampling and choice shuffle.

### Commands

`**etl refresh**` — fetch etymology-db + gloss dumps into `data/raw/` if missing or `--force`. Verify checksums. Do **not** wipe `puzzles` in Postgres. Then rebuild derived graph + gloss index (`--skip-derived` to download only).

`**etl generate**` — read derived artifacts (error if missing: tell user to `refresh`). Options:

- `--n N` (default from config; `0` = all that pass filters)
- `--seed`
- `--lang-pair en-de` (repeatable)
- `--min-quality`
- **sink (mutually exclusive):** `--stdout` (JSON for inspection), `--jsonl PATH` (default `data/puzzles/puzzles.jsonl`), `--db` (upsert into Postgres)
- `--dry-run` — counts and funnel only, no write

`**etl reset**` — regenerate from scratch, with blast radius flags:

- `--puzzles` (default) — truncate/delete puzzle rows; later **do not** drop `users`/`scores`
- `--derived` — delete `data/derived/`
- `--raw` — delete downloads (next generate must refresh)
- `--all` — raw + derived + puzzles
- `--reload` — then `refresh` + `generate --db` in one shot

Never `DROP DATABASE` from ETL. Go owns schema migrations; ETL assumes tables exist (`etl doctor` checks).

**Also ship these — they save more time than a fancier generator:**

- `**etl doctor**` — raw present + checksums, derived present, Postgres reachable, migrations applied, disk estimate.
- `**etl stats**` — edge counts by lang/reltype; puzzle counts by lang-pair; rejection reasons (`no_gloss`, `too_big`, `same_meaning`, `es_pt_trivial`, …). Write `data/reports/funnel.json`.
- `**etl inspect [id|--random|--lang-pair]**` — print one puzzle as readable text (leaves, glosses, choices, gold edges) without the UI.
- `**etl validate [PATH|--db]**` — schema, 4 choices, unique ids, graph 3–5 nodes, leaves in prompt, gold edges subset of node ids, distractors ≠ correct.
- `**etl load PATH**` — JSONL → DB upsert without regenerating (fixtures, sharing a reviewed set).
- `**etl disable ID**` — `enabled=false` after a bad eyeball (API skips these).

Optional later: `etl sample-fixture` to cut a tiny graph for CI.

### Graph rules (unchanged intent)

NetworkX (or similar): node = `(lang, term)`. Walk from modern leaves toward ancestors. Reject huge PIE soup and trivial 2-node borrows. English gloss canonical for v1.

### Operational notes

- Full refresh is tens of minutes and hundreds of MB; the common loop is `generate --stdout` / `--n 20` against derived data.
- `generate` does **not** implicit-refresh (avoids surprise downloads).
- Structured log counts per filter stage.
- Copy license notes into `data/raw/NOTICE` on refresh; UI colophon stays separate.

## Database (Postgres)

Pregenerated puzzles, not the full 4M-edge dump.

- `puzzles`: `id` (content hash), `enabled` (default true), one row usable as both modes, `leaf_a`/`leaf_b`, `answer_graph` (gold; prompt derived at serve time), `choices`, `correct_choice`, `quality_score`, `lang_pair`, `source`.
- Hard mode can reuse the same `answer_graph`; API strips edges (and maybe ancestor labels) depending on mode. Do not duplicate gold as a stored `prompt_graph`.
- Empty `users` / `scores` tables only if you want migrations ready; no auth in v1.

## Backend: Go (not Python)

The API is a thin JSON layer over pregenerated rows. Python stays **only** for ETL. A second language is justified here: the ETL is a batch graph/NLP job; the server is long-lived HTTP + Postgres + (later) sessions.

### Alternatives considered

This v1 API is ~two endpoints, JSON in/out, `jsonb` graphs, CORS, later cookie/JWT auth and leaderboards. All four stacks can do that. Differences are operational weight and how well they fit *later* features.

- **Go (chosen).** `net/http` (Go 1.22+ routing) or Chi; `pgx` for Postgres; `encoding/json` for graphs. Single static binary in Docker, fast compile, trivial random-row + edge-set compare. Auth later: middleware + sessions (e.g. `gorilla/sessions` or JWT). Leaderboards: SQL `ORDER BY score`. No runtime to babysit. Weakest fit only if you later want Phoenix-style live presence as a first-class feature.
- **Elixir / Phoenix.** Best of this list for live leaderboards, presence, and channels. JSON + Ecto + Postgres is excellent. Cost: BEAM, Mix, a second ecosystem beside Python and Node, and more moving parts than the v1 endpoints need. Strong upgrade path *if* realtime becomes core.
- **Java / Spring Boot.** Unbeatable library coverage (Spring Security, JPA). For two endpoints it is heavy: JVM image, annotation/config surface, slower inner loop than Go. Reasonable if you already live in Spring; otherwise overkill.
- **Scala (http4s or Play, circe, doobie/skunk).** Nicest typed JSON codecs for `answer_graph`. Smallest pool of tooling/help, sbt/Mill complexity, and slower iteration than Go for a CRUD-shaped API. Skip unless you want FP/types as a personal goal.

TypeScript/Node was not requested; it would share types with React but you asked to leave Python *and* pick among JVM/Go/BEAM.

### Go shape for v1

- `GET /puzzles/random?mode=easy|hard` — prompt without `correct_choice` / gold edges.
- `POST /puzzles/{id}/solve` — `{ choiceId }` or `{ edges: [{from, to}] }`; returns `{ correct, goldGraph, choices }`.
- `pgx` + a small migrations tool (`goose` or `atlas`).
- CORS for Vite. Docker: scratch/distroless binary.
- Never send the gold answer on GET. Graph check: canonicalize node ids, compare directed edge sets (ignore layout).

OpenAPI is optional; a shared JSON example in `backend/openapi.yaml` or `packages/puzzle-schema.json` is enough until auth exists.

## Frontend: React + TypeScript + Vite + React Flow

- Home: pick easy / hard (two paper folders or stamped buttons).
- Easy: two word **index cards**, four meaning **post-its**, then **read-only** React Flow on a desk blotter (nodes as cards; edges as ink strokes).
- Hard: same canvas; **leaves locked**; ancestor cards in a post-it palette; connect with ink; Submit stamp. 3–5 nodes only.
- Attribution footer (Wiktionary / CC BY-SA) as a typeset colophon.
- Shared graph component for reveal vs editor (one `nodes`/`edges` model). Custom React Flow node/edge types so the graph uses the same tokens as the rest of the UI.

### Design system (paper, ink, typewriter)

A **small token + primitive layer** in `frontend/src/ui/` — not a skeuomorphic theme pack. Screens compose primitives; new modes add layouts, not new palettes.

**Color tokens** (CSS variables, cream desk not pure white):

- `--paper`, `--paper-ruled`, `--paper-kraft` — page backgrounds
- `--ink`, `--ink-muted`, `--ink-faint` — near-black / graphite (WCAG AA on paper)
- `--rule` — hairline for underlines and card edges
- Post-it accents, one each, low saturation so type stays readable: `--note-yellow`, `--note-pink`, `--note-blue`, `--note-green` (MC options / palette items)
- `--stamp-red` — primary actions and wrong-state, used sparingly
- No dark theme in v1 (paper metaphor breaks); high-contrast ink on cream is the accessibility story

**Type:** typewriter-inspired but **legible**. Skip novelty “Special Elite”-only UI.

- **IBM Plex Mono** — words, language tags, buttons, graph labels (fixed-width, typewriter feel)
- **IBM Plex Serif** — longer glosses and help text (ink-on-paper, easier than all-mono)
- Tracking slightly open on stamps/labels; body at 16–18px; avoid all-caps paragraphs

**Motion/texture:** almost none. 1–2px paper stack offset, optional 0.5–1° tilt on post-its only. No torn-edge PNGs, no paper-grain wallpaper (noise filters fight React Flow). Edges = 1px `--rule`, not drop shadows.

**Primitives (extensible set):**

- `Sheet` — full “page” / desk
- `IndexCard` — puzzle words, graph nodes
- `PostIt` — MC choices, hard-mode palette
- `InkButton` / `Stamp` — submit, mode pick (underline or rubber-stamp border, not Material buttons)
- `Colophon` — footer attribution
- Graph: `EtymologyNode` + `InkEdge` registered with React Flow

**Do not:** Tailwind-default purple, glassmorphism, or a second accent system per mode. Language can be a small ink stamp on a card (`EN`, `DE`), not a color-coded rainbow.

## Repo layout

- `[etl/](etl/)` — Python Typer CLI, `config.yaml`, fixtures
- `[backend/](backend/)` — Go module (`cmd/api`, `internal/...`)
- `[frontend/](frontend/)` — React (`src/ui` tokens + primitives, then screens)
- `[docker-compose.yml](docker-compose.yml)` — Postgres + Go API (+ optional frontend)

## Quality and the main risks

- **Noise:** Wiktionary parse errors → strict filters, manual spot-check of ~50 puzzles, `quality_score` + ability to disable rows.
- **Too-easy MC:** divergence filter + distractors that are plausible ancestor meanings, not random dictionary words.
- **ES/PT overlap:** require extra depth or a non-obvious LCA, or mix with EN/DE.
- **Reconstructed forms:** keep `*` on terms; gloss from Wiktionary proto entries when present.
- **Hard-mode UX:** do not ask players to guess relation types or invent nodes in v1.

## Suggested build order

1. ETL CLI + derived artifacts → `generate --stdout --n 20`; `inspect` / `validate`; then `--db` when Postgres exists.
2. Postgres + Go API random + solve.
3. Design tokens + primitives (`Sheet`, `IndexCard`, `PostIt`, `InkButton`).
4. Easy UI + graph reveal on those primitives.
5. Hard UI on the same puzzle payload and node types.
6. Docker Compose so the game runs locally.

