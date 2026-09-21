# EtymoloGuessr API

Go HTTP service that serves pregenerated etymology puzzles. Local Docker Compose still uses Postgres. Production (Railway) loads a JSONL snapshot into process memory — no hosted database.

Contract: [openapi.yaml](openapi.yaml). Go-language walkthrough: [go_noob_readme.md](go_noob_readme.md).

## Layout

```
backend/
  cmd/api/              process entrypoint (Postgres if DATABASE_URL, else JSONL)
  internal/api/         HTTP routes, CORS, JSON
  internal/catalog/     in-memory store + JSONL loader + embedded snapshot
  internal/config/      env vars (PORT, HTTP_ADDR, DATABASE_URL, PUZZLES_PATH)
  internal/db/          pgx pool, migrations, queries
  internal/puzzle/      prompt stripping and scoring
  openapi.yaml
  Dockerfile
  railway.json
```

## What it stores

Table `puzzles` (created on API startup when `AUTO_MIGRATE` is true). Columns match `etl/store/db.py` upserts:

| Column | Role |
|---|---|
| `id` | Content hash from ETL; primary key |
| `enabled` | API skips `false` (`etl disable`) |
| `leaf_a` / `leaf_b` | JSONB terms shown to the player |
| `answer_graph` | Gold nodes + directed edges. **Not** returned on GET |
| `choices` / `correct_choice` | Four-way MC; gold id hidden until solve |
| `quality_score` / `lang_pair` / `source` | Filters and provenance |

Gold lives only in `answer_graph`. The player prompt is derived at serve time (`nodes` from gold, `edges: []`). There is no `prompt_graph` column.

Empty `users` and `scores` tables exist so later auth/leaderboards do not require a rewrite. ETL must never drop them.

## Endpoints

Base URL defaults to `http://localhost:8080`. JSON field names on the wire are camelCase (`leafA`, `choiceId`). Graph node/edge objects keep the ETL keys (`from`, `to`, `reltype`).

### `GET /health`

When `DATABASE_URL` is set, pings Postgres (`503` if down). When serving JSONL, this is process-up only. `200 {"status":"ok"}`.

### `GET /puzzles/random`

Query:

| Param | Default | Notes |
|---|---|---|
| `mode` | `easy` | `easy`, `medium`, or `hard` |
| `langPair` | (any) | e.g. `de-en` |
| `minQuality` | (any) | integer vs `quality_score` |

Only `enabled = true` rows. `404` if none match.

**Never included:** `correctChoice`, gold edges.

| Mode | `promptGraph` |
|---|---|
| `easy` | Omitted. The two words are `leafA` / `leafB`; the graph is only in the solve response (`goldGraph`) |
| `medium` | Omitted. Eight opaque leaf tokens are returned in `leaves`; the four-puzzle set id is returned as `id` |
| `hard` | All nodes with glosses kept; `edges: []`. Terms stay so the player can place known ancestor cards |

`choices` are always sent (unmarked). Hard UI can ignore them.

### `GET /puzzles/{id}`

Query:

| Param | Default | Notes |
|---|---|---|
| `mode` | `easy` | `easy`, `medium`, or `hard` |

Same prompt as random for that id: Easy omits `promptGraph`; Medium returns the eight leaves in the requested puzzle set; Hard sends all nodes with glosses kept, empty edges. Never `correctChoice` or gold edges.

The UI lock re-fetches this after refresh. `404` if the puzzle is missing, disabled, or not eligible for the mode (Hard needs ≥ 4 nodes) — that clears a lock when `generate --db` replaced the table. Invalid `mode` → `400`.

### `POST /puzzles/{id}/solve`

Disabled or missing ids → `404`. Body:

Easy:

```json
{ "mode": "easy", "choiceId": "c0" }
```

Hard (directed edge set; order and `reltype` ignored):

```json
{
  "mode": "hard",
  "edges": [
    { "from": "English:father", "to": "Proto-Germanic:*fader" },
    { "from": "German:Vater", "to": "Proto-Germanic:*fader" }
  ]
}
```

Response includes `correct`, `goldGraph`, `choices`, `correctChoice`.

Medium:

```json
{
  "mode": "medium",
  "pairs": [["leaf-token-a", "leaf-token-b"], ["leaf-token-c", "leaf-token-d"], ["leaf-token-e", "leaf-token-f"], ["leaf-token-g", "leaf-token-h"]]
}
```

The response includes `correct`, `ancestors`, and `pairOrigins`; it does not reveal the gold graph.

CORS: `GET`, `POST`, `OPTIONS` from origins in `CORS_ORIGINS` (Vite defaults).

## Run locally

Needs Go 1.24+. Local play stack still wants Postgres 16 (`docker compose up db -d`). Production and `go run` without `DATABASE_URL` serve the embedded catalog.

```bash
# JSONL in-process (no Postgres) — uses backend/internal/catalog/puzzles.jsonl
cd backend
go run ./cmd/api

# or a file you just generated
PUZZLES_PATH=../data/puzzles/puzzles.jsonl go run ./cmd/api
```

Postgres (Compose DSN):

```bash
# from repo root
docker compose up db -d

export DATABASE_URL=postgres://etymologuessr:etymologuessr@localhost:5432/etymologuessr?sslmode=disable
export CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

cd backend
go run ./cmd/api
```

Load puzzles (ETL, repo root). JSONL and Postgres are separate: `generate --jsonl` does not touch the DB; `generate --db` re-walks derived data, truncates `puzzles` and `scores`, then upserts (it does not read JSONL).

```bash
# reuse a file you already generated (upsert; does not truncate)
uv run etl load data/puzzles/puzzles.jsonl
# extract from derived into Postgres only (replaces puzzle rows; does not write or read JSONL)
uv run etl generate --db --n 50 --seed 1
```

Smoke:

```bash
curl -s http://localhost:8080/health
curl -s 'http://localhost:8080/puzzles/random?mode=easy'
curl -s "http://localhost:8080/puzzles/${ID}?mode=easy"
```

### Docker (API + Postgres)

From the repository root:

```bash
docker compose up --build
```

API is `:8080`, Postgres `:5432`. Schema is applied when the API container starts, but the database starts empty. Load the committed catalog from another terminal before playing:

```bash
DATABASE_URL=postgres://etymologuessr:etymologuessr@localhost:5432/etymologuessr?sslmode=disable \
  uv run etl load backend/internal/catalog/puzzles.jsonl
```

For the simplest local play loop, omit Docker and Postgres: `go run ./cmd/api` serves the same committed catalog in process.

### Tests

```bash
cd backend
go test ./...
```

HTTP tests use `catalog.MemoryStore` (same type as JSONL production). Scoring and prompt stripping are unit-tested in `internal/puzzle`. Store and `/health` tests against Postgres skip unless `TEST_DATABASE_URL` is set (throwaway compose on port 5433; see the root README). Run `go test -p 1 ./...` when that DSN is set so package tests do not share the database in parallel.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | unset | Postgres DSN. If set, the API uses Postgres (local Compose). If unset, JSONL catalog. |
| `PUZZLES_PATH` | (embedded `puzzles.jsonl`) | JSONL file when `DATABASE_URL` is unset. Ignored when Postgres is configured. |
| `PORT` | (none) | Listen port (Railway). Wins over `HTTP_ADDR`. Digits only → `:PORT`. |
| `HTTP_ADDR` | `:8080` | Listen address when `PORT` is unset |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated; `*` allows any Origin |
| `AUTO_MIGRATE` | `true` | Apply `internal/db/migrations/*.sql` on boot (Postgres only) |

To refresh the committed snapshot after a full generate:

```bash
cp data/puzzles/puzzles.jsonl backend/internal/catalog/puzzles.jsonl
```

## Migrations

SQL files in `internal/db/migrations/` are embedded in the binary and applied in filename order. Applied versions go in `schema_migrations`. Files may use `-- +goose Up` / `-- +goose Down` markers; only the **Up** section is executed. Down exists for documentation / a future CLI, not for boot.

Do not `DROP DATABASE` from ETL. `etl reset --puzzles` truncates `puzzles` and `scores` (FK) but never drops those tables or `users`.

## License

Puzzle data is derived from [etymology-db](https://github.com/droher/etymology-db) (CC BY-SA 3.0) plus Wiktionary/kaikki glosses. Share-alike still applies to served puzzle JSON.
