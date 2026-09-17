# EtymoGuessr API

Go HTTP service that serves pregenerated etymology puzzles from Postgres. It does not walk the Wiktionary graph: Python ETL writes rows, this process picks one, hides the answer, and grades a submission.

Contract: [openapi.yaml](openapi.yaml). Go-language walkthrough: [go_noob_readme.md](go_noob_readme.md).

## Layout

```
backend/
  cmd/api/              process entrypoint
  internal/api/         HTTP routes, CORS, JSON
  internal/config/      env vars
  internal/db/          pgx pool, migrations, queries
  internal/puzzle/      prompt stripping and scoring
  openapi.yaml
  Dockerfile
```

## What it stores

Table `puzzles` (created on API startup when `AUTO_MIGRATE` is true). Columns match `etl/db.py` upserts:

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

Pings Postgres. `200 {"status":"ok"}` or `503`.

### `GET /puzzles/random`

Query:

| Param | Default | Notes |
|---|---|---|
| `mode` | `easy` | `easy` or `hard` |
| `langPair` | (any) | e.g. `de-en` |
| `minQuality` | (any) | integer vs `quality_score` |

Only `enabled = true` rows. `404` if none match.

**Never included:** `correctChoice`, gold edges, ancestor meanings that would give away the MC answer.

| Mode | `promptGraph` |
|---|---|
| `easy` | Omitted. The two words are `leafA` / `leafB`; the graph is only in the solve response (`goldGraph`) |
| `hard` | All nodes; ancestor `gloss` stripped; `edges: []`. Terms stay so the player can place known ancestor cards |

`choices` are always sent (unmarked). Hard UI can ignore them.

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

CORS: `GET`, `POST`, `OPTIONS` from origins in `CORS_ORIGINS` (Vite defaults).

## Run locally

Needs Go 1.24+ and Postgres 16.

```bash
# from repo root
docker compose up db -d

export DATABASE_URL=postgres://etymoguessr:etymoguessr@localhost:5432/etymoguessr?sslmode=disable
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
```

### Docker (API + Postgres)

```bash
docker compose up --build
```

API is `:8080`, Postgres `:5432`. Schema is applied when the API container starts.

### Tests (no database)

```bash
cd backend
go test ./...
```

HTTP tests use an in-memory store. Scoring and prompt stripping are unit-tested in `internal/puzzle`.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | required | Postgres DSN (`sslmode=disable` for local Compose) |
| `HTTP_ADDR` | `:8080` | Listen address |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated; `*` allows any Origin |
| `AUTO_MIGRATE` | `true` | Apply `internal/db/migrations/*.sql` on boot |

## Migrations

SQL files in `internal/db/migrations/` are embedded in the binary and applied in filename order. Applied versions go in `schema_migrations`. Files may use `-- +goose Up` / `-- +goose Down` markers; only the **Up** section is executed. Down exists for documentation / a future CLI, not for boot.

Do not `DROP DATABASE` from ETL. `etl reset --puzzles` truncates `puzzles` and `scores` (FK) but never drops those tables or `users`.

## License

Puzzle data is derived from [etymology-db](https://github.com/droher/etymology-db) (CC BY-SA 3.0) plus Wiktionary/kaikki glosses. Share-alike still applies to served puzzle JSON.
