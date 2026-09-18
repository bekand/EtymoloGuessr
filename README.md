# EtymoloGuessr

A guessing game about etymology. You are shown two modern words (English, Spanish, Portuguese, or German) that share an ancestor, and you try to recover that connection.

**Easy** asks you to pick the shared ancestor’s meaning from four choices. **Medium** asks you to pair eight words by their shared ancestors. **Hard** gives you the words and asks you to place the ancestors and draw the edges yourself. Every mode reveals feedback about the shared ancestry after submission.

Puzzles are built offline from Wiktionary-derived etymology data. The live game never walks that graph: Python ETL writes puzzle rows, a Go API serves one at a time (hiding the answer until you submit), and a React UI plays the round.

Puzzle data is derived from [etymology-db](https://github.com/droher/etymology-db) (CC BY-SA 3.0) plus Wiktionary / kaikki glosses. Attribution belongs in the UI; share-alike still applies to derived puzzles.

## Repository layout

```
etl/            Python CLI: download dumps, filter the graph, emit puzzles
backend/        Go HTTP API (Postgres locally; JSONL catalog in production)
frontend/       React + Vite UI (home, easy, medium, hard)
data/           Local artifacts (raw dumps, derived graph, puzzle JSONL) — not in git
etl/tests/      ETL pytest (offline + optional Postgres)
docker-compose.yml        Postgres 16 + API (play stack, :5432 / :8080)
docker-compose.test.yml   Throwaway Postgres + API for tests (:5433 / :18080)
```

Each layer has its own README for commands, env vars, and internals:

- [etl/README.md](etl/README.md)
- [backend/README.md](backend/README.md)
- [frontend/README.md](frontend/README.md)

## Dependencies

**To run locally**

| Tool | Why |
|---|---|
| [Docker](https://docs.docker.com/get-docker/) | Postgres 16 and the API (`docker compose`) |
| [uv](https://docs.astral.sh/uv/) + Python 3.11+ | ETL CLI (`uv sync` from the repo root) |
| [pnpm](https://pnpm.io/) + Node.js | Frontend |

Go 1.24+ is only needed if you run the API outside Docker (`go run ./cmd/api`).

**What each layer uses**

| Layer | Stack |
|---|---|
| ETL | Typer, PyYAML, NetworkX, pandas, PyArrow, psycopg, httpx |
| API | Go stdlib `net/http`, [pgx](https://github.com/jackc/pgx) |
| UI | React 19, Vite, TypeScript, Sass, TanStack Query, React Flow, React Router, IBM Plex |
| Data | Postgres 16 locally; JSONL in-process on Railway |

## Run locally

From the repo root. This uses fixture data (no Wiktionary dump download) so you can play immediately.

```bash
uv sync
docker compose up --build -d
```

Wait until `http://localhost:8080/health` returns ok (the API applies the schema on boot), then load fixture puzzles:

```bash
uv run etl reset --all --reload --fixtures
```

To load real Wiktionary-derived puzzles instead of fixtures, see [etl/README.md](etl/README.md).

Then:

```bash
cd frontend
pnpm install
pnpm dev
```

Open the URL Vite prints (usually `http://localhost:5173`). The UI proxies `/api` to the Go service on port 8080.

Postgres is on `localhost:5432` (`etymologuessr` / `etymologuessr`). To stop the containers: `docker compose down`.

## Tests

Each layer owns its suite. Offline tests need no Docker:

```bash
uv run pytest -m "not integration"   # ETL
cd backend && go test ./...          # API (Postgres cases skip without TEST_DATABASE_URL)
cd frontend && pnpm test             # Vitest unit + MSW
```

Integration and browser tests use a throwaway stack so they never truncate the play database on 5432:

```bash
docker compose -f docker-compose.test.yml up -d --wait --build
export TEST_DATABASE_URL=postgres://etymologuessr:etymologuessr@localhost:5433/etymologuessr?sslmode=disable
uv run pytest -m integration
cd backend && TEST_DATABASE_URL=$TEST_DATABASE_URL go test -p 1 ./...
cd frontend && pnpm exec playwright install chromium && pnpm test:e2e
```

Wait until `http://localhost:18080/health` is ok before the Playwright run (it loads fixtures into the test database). The e2e UI uses `VITE_API_URL=http://localhost:18080`.

## Deploy (Railway)

Two services, **no Railway Postgres**. ETL stays on your machine. Catalog updates are: regenerate JSONL, copy into the API embed, redeploy.

1. Generate puzzles locally (`uv run etl refresh` then `uv run etl generate --jsonl data/puzzles/puzzles.jsonl`) and copy the snapshot:

   ```bash
   cp data/puzzles/puzzles.jsonl backend/internal/catalog/puzzles.jsonl
   ```

   The repo ships a tiny fixture snapshot so the API still boots without a full dump.

2. Create a Railway project with two services from this repo:

   | Service | Root directory | Notes |
   |---|---|---|
   | **api** | `backend` | Dockerfile. Unset `DATABASE_URL`. `CORS_ORIGINS` = public **web** URL (no trailing slash). Railway injects `PORT`. Enable Serverless. |
   | **web** | `frontend` | Dockerfile. Build arg / variable `VITE_API_URL` = public **api** URL (no trailing slash). Enable Serverless. |

3. Deploy **api** first, copy its `*.up.railway.app` URL into the web service `VITE_API_URL`, then deploy **web**. Put the web URL on the api service `CORS_ORIGINS` and redeploy api if you guessed the web URL wrong.

`GET https://<api>/health` is process-up (no Postgres). `/easy`, `/medium`, and `/hard` are SPA routes (Caddy `try_files`). Custom domains need Railway Hobby; free plan is `*.up.railway.app` only.

Do not run `etl` on Railway. Do not add a database plugin for v1.
