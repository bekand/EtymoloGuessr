---
name: Etymology game plan
overview: "EtymoGuessr v1 is playable locally: Python ETL, Go API + Postgres, React paper/ink UI (Easy MC + Hard graph editor). Remaining work is puzzle quality (homographs, case-qualifier glosses) and a diamond test suite."
todos:
  - id: etl-cli
    content: "Python Typer CLI: refresh, generate (--n, stdout/jsonl/db), reset, doctor, stats, inspect, validate, load, disable"
    status: completed
  - id: etl-reduce
    content: Filter languages/reltypes, persist cleaned graph + gloss index as reusable artifacts
    status: completed
  - id: etl-puzzles
    content: Extract LCA puzzles, quality filters, MC distractors, hashed ids, rejection funnel
    status: completed
  - id: db-api
    content: Postgres puzzle schema + Go API GET random/by-id / POST solve (hide gold until submit)
    status: completed
  - id: design-system
    content: Paper/ink tokens + primitives (Sheet, IndexCard, PostIt, InkButton, Stamp, Colophon, graph)
    status: completed
  - id: frontend-easy
    content: "React easy mode: two words, MC, React Flow reveal with reltype labels"
    status: completed
  - id: frontend-hard
    content: "Hard mode: all nodes in palette, place then draw child→ancestor edges, score exact edge-set"
    status: completed
  - id: compose
    content: Docker Compose for Postgres + API; CC BY-SA attribution in UI
    status: completed
  - id: skip-case-qualifiers
    content: Strip/skip Wiktionary [with genitive]-style case-government glosses in first_gloss; reject leftover qualifier-only LCAs
    status: pending
  - id: homograph-allowlist
    content: Gloss-aligned ancestor-edge allowlist from kaikki etymology_templates so mixed-etymology nodes (English son) walk the sense that matches the stored gloss
    status: pending
  - id: diamond-tests
    content: "Diamond suite: move ETL tests under etl/tests/, Vitest/Playwright, Postgres integration, CI"
    status: pending
  - id: doc-sync
    content: "Catch up frontend README (Hard + Router), etl README defaults (n=0, min_quality=4), OpenAPI GET /puzzles/{id}"
    status: pending
isProject: false
---

# EtymoGuessr

**Status:** v1 is playable locally. Python ETL writes puzzle rows, a Go API serves one at a time (hiding the answer until submit), and a React UI plays Easy and Hard. This plan is the product/architecture source of truth; layer READMEs hold commands.

Wiktionary-derived data is noisy and **has no meanings**, so the pipeline joins glosses from kaikki/wiktextract and **prefers semantic-shift pairs** so multiple-choice is not trivial (EN *father* / DE *Vater* both mean “father”).

## Product (v1, shipped)

**Easy** (`/easy`): two modern words (EN / ES / PT / DE) on index cards → pick the common ancestor’s meaning from 4 post-its → on submit, cards/choices hide and a read-only etymology graph appears (ink edges **with** relation labels). Index cards have an Explain control for the leaf gloss.

**Hard** (`/hard`): same puzzle family, but only rows with **≥ 4 graph nodes**. **No nodes start on the blotter** — leaves and ancestors all sit in a post-it palette. Place every card (click or drag), then draw directed edges **child → ancestor**. Player edges have no relation-type labels. Submit is disabled until every node is placed (hint: “Build the graph!”). Score is an exact directed edge-set match (ignore order and `reltype`).

**Home** (`/`): Easy / Hard stamps. React Router, not in-memory screen state.

**Out of scope for v1:** accounts, scoring persistence, leaderboards (`users` / `scores` tables exist so later work does not rewrite schema). Daily challenge / explore-the-full-graph can wait. No dark theme (paper metaphor). Partial credit for hard edges (precision/recall) is optional later.

**License:** etymology-db is [CC BY-SA 3.0](https://github.com/droher/etymology-db). Attribute Wiktionary + etymology-db in the UI colophon; derived puzzle data stays share-alike. Do **not** commit `data/puzzles/` snapshots.

## Why not query the live etymology graph at request time

Pregenerate puzzles. Serving is “pick a row, hide the answer, check a submission.” The graph walk, LCA search, gloss join, and distractor generation are slow, messy, and should be inspectable offline.

```mermaid
flowchart LR
  refresh[etl refresh]
  raw[data/raw]
  graph[data/derived graph plus glosses]
  gen[etl generate]
  out[stdout or JSONL]
  pg[(Postgres puzzles)]
  api[Go API]
  ui[React Vite]
  refresh --> raw
  raw --> graph
  graph --> gen
  gen --> out
  gen --> pg
  pg --> api
  api --> ui
```

**Local loop:** `docker compose up --build -d` (Postgres 16 + API on `:8080`), `uv run etl reset --all --reload --fixtures` for a tiny playable set, `cd frontend && pnpm dev` (Vite proxies `/api` → `:8080`). Full Wiktionary puzzles: `etl refresh` then `etl generate --db` (see [etl/README.md](etl/README.md)). Frontend is **not** in Compose.

## Data pipeline (Python CLI) — as built

Typer app: `uv run etl …`. Staged artifacts so generate does not re-download or rebuild the graph every time. Config in [etl/config.yaml](etl/config.yaml). `DATABASE_URL` overrides `database_url` in config. Large dumps stay in `data/` and are **gitignored**; pin source URLs in config (checksums optional, currently unset).

Source: [droher/etymology-db](https://github.com/droher/etymology-db) (`etymology.parquet`, Dec 2023). Edges: `term` / `lang` → `reltype` → `related_term` / `related_lang`. Glosses from [kaikki.org](https://kaikki.org/) / wiktextract. English gloss is canonical for v1.

### Layout

- `data/raw/` — parquet, gloss JSONL, checksums, `manifest.json`, `NOTICE`
- `data/derived/` — filtered edges parquet, `gloss_index.json`, `lemma_index.json`
- `data/puzzles/` — optional JSONL snapshots (not in git)
- `data/reports/` — `funnel.json`, `stats.json`
- `etl/fixtures/` — tiny committed slice for tests and `--fixtures`

### Current generate defaults (`etl/config.yaml`)

- `n: 0` — emit every survivor (full pass)
- `min_quality: 4`
- `max_nodes: 9` (graphs larger than 9 are `too_big`; no minimum at generate time)
- `n_choices: 4`
- `seed: 89`

### Stages

1. **Reduce graph** — leaf langs English / Spanish / Portuguese / German; ancestor allowlist in config (Latin through PIE, plus Ancient Greek, Arabic, Hebrew, Persian, Nahuatl, Sanskrit, …); keep `inherited_from`, `borrowed_from`, `derived_from`, `root`, `cognate_of`, `doublet_with`; drop null related terms, MWEs, affix noise.
2. **Index glosses** — first *lexical* gloss per `(lang, term)`; skip `form_of` / grammatical-form senses; join colon-ending qualifier lists onto the continuation (`Of a person:` + `smug` → one gloss). Form-only entries inherit the citation lemma’s gloss and are recorded in `lemma_index.json`.
3. **Extract puzzles** — two modern leaves and their closest connecting subgraph / LCA. Ancestor walks use `inherited_from` / `borrowed_from` / `derived_from` / `root` only.
4. **Ids** — SHA-256 of `(leaf_a, leaf_b, lca, gold edges)` so `etl load` upserts instead of duplicating. `--seed` for sampling and choice shuffle.

### Quality score (integer 0–5)

Start at 5:

| Penalty | Points |
|---|---|
| Same leaf language | −3 (same-lang pairs top out at **2**, so default `min_quality` 4 drops them) |
| Spanish–Portuguese whose leaf terms share the first 3 characters | −2 (unrelated ES–PT pairs are not penalized) |
| LCA is a modern leaf language (EN/ES/PT/DE) | −1 |
| High overlap (either leaf **term** still appears as a content token in the LCA gloss) | −1 |

### Filters that stuck (rejection funnel)

- **Proper-noun leaves** — EN/ES/PT term starts uppercase (`proper_noun_leaf`). German exempt.
- **Short / unglossed LCA** — term < 3 chars (`lca_term_too_short`); missing gloss (`no_gloss`).
- **Form-only LCA** — rewrite gold node to the citation lemma (`Latin:addere` → `Latin:addō`); leftover grammatical glosses (`accusative … of …`) → `inflection_lca`. Lexical homographs stay (*factum* “deed”, not *faciō*).
- **Leaf = LCA** — first content word of either leaf term/gloss equals first content word of LCA term/gloss (`lca_equals_leaf`). Catches *dragon* vs “dragon, monster”.
- **Same meaning** — both leaf terms still appear in the LCA gloss (`same_meaning`). Function words ignored.
- **Leaf reuse** — each `(lang, term)` appears as a leaf in at most one puzzle per `generate` batch.
- **Distractors** — from other candidates’ LCA glosses. Fewer than 3 distinct real glosses → `insufficient_distractors` (**no placeholders**).

### Commands (behavior that matters)

- `etl refresh` — fetch dumps if missing (`--force` re-download); then rebuild derived. `--fixtures` copies `etl/fixtures/` (no network). Does **not** wipe Postgres puzzles. `--skip-derived` downloads only.
- `etl generate` — reads derived only (errors if missing). Sinks are mutually exclusive: `--stdout` / `--jsonl PATH` / `--db`. Default file sink is `data/puzzles/puzzles.jsonl`. `--dry-run` = funnel only.
- **JSONL and Postgres are separate.** `generate` never reads an existing puzzle file. `generate --db` **truncates `puzzles` and `scores`** (FK), then upserts from a fresh graph walk — so rejected leftovers (old inflection LCAs) disappear. `etl load PATH` upserts a file without truncate or regenerate.
- `etl reset` — never `DROP DATABASE` or drop `users` / `scores` tables. `--puzzles` truncates puzzle + score rows. `--reload` force-refreshes, generates, writes JSONL, and `--db`.
- Also: `doctor`, `stats`, `inspect`, `validate`, `disable`. Go owns schema migrations; ETL assumes `puzzles` exists (`etl doctor` checks). A missing DB does not fail doctor (JSONL-only is valid).

`generate --n > 0` early-exits once enough survivors exist. `--n 0` is the full pass. The API has **no puzzle cache**; after `--db`, the next `GET /puzzles/random` sees new rows. The UI may still show a locked id until 404 / Next.

## Database (Postgres)

Pregenerated puzzles only — not the 4M-edge dump.

- `puzzles`: `id` (content hash), `enabled` (default true), `leaf_a` / `leaf_b`, `answer_graph` (gold; prompt derived at serve time), `choices`, `correct_choice`, `quality_score`, `lang_pair`, `source`.
- **Canonical gold is `answer_graph` only.** No `prompt_graph` column or JSONL field. Load rejects payloads that still include `prompt_graph`.
- Empty `users` / `scores` for later auth/leaderboards. ETL must never drop those tables.

## Backend: Go — as built

Thin JSON over pregenerated rows. Python stays **only** for ETL. Stack: Go 1.24+ `net/http`, `pgx`, embedded SQL migrations (`AUTO_MIGRATE=true` on boot). Single binary in Docker. CORS for Vite.

### Endpoints

- `GET /health` — ping Postgres.
- `GET /puzzles/random?mode=easy|hard` — only `enabled = true`. Query: `langPair`, `minQuality`. Hard also requires **≥ 4 nodes**. `404` if none match.
- `GET /puzzles/{id}?mode=` — used by the UI puzzle lock to re-fetch after refresh; 404 clears the lock if `--db` deleted the row. (OpenAPI does not list this yet.)
- `POST /puzzles/{id}/solve` — `{ mode, choiceId }` or `{ mode, edges }`; returns `{ correct, goldGraph, choices, correctChoice }`.

**Never send gold on GET.** Easy omits `promptGraph` entirely (the two words are `leafA` / `leafB`). Hard sends all nodes, ancestor `gloss` stripped, `edges: []`. Terms stay so the player can place known ancestor cards. `choices` always go out unmarked; Hard UI ignores them.

Graph check: canonicalize node ids, compare directed edge sets (ignore layout and `reltype`).

OpenAPI: [backend/openapi.yaml](backend/openapi.yaml). Tests: in-memory store + `internal/puzzle` unit tests (`go test ./...`).

## Frontend: React + TypeScript + Vite — as built

- pnpm, React 19, Sass tokens (no Tailwind), IBM Plex Mono + Serif, TanStack Query, React Flow, React Router, React Compiler.
- Routes: `/`, `/easy`, `/hard`.
- Primitives in `frontend/src/ui/`: `Sheet`, `IndexCard`, `PostIt`, `InkButton`, `Stamp`, `Colophon`, `EtymologyNode` + `InkEdge`.
- Easy and Hard share `FeedbackScreen` (verdict + gold graph).
- Puzzle lock in `localStorage` so refresh does not swap the round. Choice order and post-it colors shuffle from the puzzle id.
- Responsive breakpoints: mobile / tablet / desktop (`_breakpoints.scss`).

### Design system (paper, ink, typewriter)

Unchanged intent. Cream desk, graphite ink, low-sat post-its, stamp-red used sparingly. No dark theme. Language is an ink stamp on a card (`EN`, `DE`), not a color-coded rainbow. Motion is almost none (stack offset, slight post-it/stamp tilt).

## Repo layout

- [etl/](etl/) — Python Typer CLI, `config.yaml`, fixtures
- [backend/](backend/) — Go module (`cmd/api`, `internal/...`)
- [frontend/](frontend/) — React (`src/ui` primitives, `src/features` screens)
- [tests/](tests/) — ETL pytest (planned move to `etl/tests/`)
- [docker-compose.yml](docker-compose.yml) — Postgres + API only

## Quality risks (still true)

- **Noise:** Wiktionary parse errors → filters, `quality_score`, `etl disable`.
- **Too-easy MC:** divergence / identity filters + real LCA-gloss distractors.
- **ES/PT overlap:** 3-character prefix −2, plus identity filters; mix with EN/DE via quality sort.
- **Reconstructed forms:** keep `*` on terms; gloss from proto entries when present.
- **Hard-mode UX:** do not ask players to guess relation types or invent nodes.
- **Homographs:** one node id per `(lang, term)` collapses senses (English *son* = offspring gloss + Spanish-music edge). Fix planned below; do not skip all mixed leaves.
- **Case-government glosses:** kaikki stores `[with genitive]` as the first gloss part; that can become the MC answer until `first_gloss` skips/strips those qualifiers.

## Decisions that diverged from the original plan

These are settled. Do not silently revert them.

| Topic | Original | Current |
|---|---|---|
| Graph size | 3–5 nodes | **Max 9**; no generate-time minimum. Hard API filters **≥ 4 nodes** (3-node “two leaves + one LCA” was trivial once leaves were unplaced). |
| Hard UX | Leaves locked on the blotter; drag 1–3 ancestors | **All nodes start in the palette**; place then connect. |
| Relation labels | None on edges in v1 | **Shown on gold/reveal**; still none while the player draws Hard edges. |
| `prompt_graph` | Derive at serve time | Confirmed; Easy **omits** `promptGraph` (leaf-only graph was redundant). |
| `generate --db` | Upsert | **Truncate puzzles + scores, then replace.** `load` is the merge path. |
| `min_quality` | TBD | Config **4**. |
| ES–PT quality | Always penalize | **−2 only if first 3 chars of leaf terms match.** |
| Same-meaning | Gloss Jaccard | Leaf **term token** in LCA gloss; identity via **first content word**. |
| Form-only LCA | Skip / `no_gloss` | **Rewrite node to citation lemma**; keep lexical homographs. |
| Navigation | React state screens | **React Router** `/` `/easy` `/hard`. |
| Compose frontend | Optional in compose | **Local Vite only.** |
| Distractors | Plausible LCAs | **No placeholders.** |
| `n` default | Sample size | **0 = all survivors.** |
| OpenAPI | Optional | Shipped (minus `GET /puzzles/{id}`). |

Backend language (Go, not Python/Elixir/Spring) is unchanged. Alternatives considered in the original plan still stand if this is ever revisited.

## Remaining work

Priority order for the next slice of product work:

1. **Skip case-government glosses** — in `first_gloss`, treat leading `[with genitive]` / `[of place]` / similar as not the meaning (use the next part, or strip the prefix, or skip qualifier-only senses). Generate-time safety net: leftover qualifier-only LCA glosses → `inflection_lca`. Fold coverage into existing grammatical-form tests; then `etl refresh` + `generate --db`. Separate plan: skip-case-qualifiers.
2. **Homograph allowlist** — parse kaikki `inh`/`bor`/`der`/`root` templates with the winning gloss; drop dump ancestor edges whose `related_term` is not in that list; fallback if filtering would isolate the node. Keep one node per spelling; do **not** skip the ~448 mixed inh+bor leaves (most are one sense listed as inherit+borrow). Separate plan: son-homograph-diagnosis.
3. **Diamond test suite** — keep existing ETL + Go unit tests; move `tests/` → `etl/tests/`; add a few Vitest cases, Postgres integration (throwaway compose on 5433 so play data on 5432 is untouched), MSW Easy round, Playwright Easy + Hard (Hard can click-to-place, avoid HTML5 drag). Separate plan: diamond-test-suite.
4. **Doc sync** — [frontend/README.md](frontend/README.md) still says Hard is a stub and there is no router; [etl/README.md](etl/README.md) still quotes `min_quality` 3 / `n` 50; OpenAPI should list `GET /puzzles/{id}`.

Known polish, not blocking: stamp click near the animated border can miss; after `--db` the UI lock may hold a deleted id until 404/Next.

## Suggested next build order

1. Case-qualifier glosses + regenerate into Postgres; eyeball Easy for leftover `[with …]` answers.
2. Gloss-aligned homograph allowlist + *son* fixture; regenerate.
3. Diamond tests + CI.
4. Doc sync (or do it alongside 1–3).
5. Then, if v1 still feels solid: accounts / scores / daily — not before.
