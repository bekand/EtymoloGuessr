# EtymoGuessr

A guessing game about etymology. You are shown two modern words (English, Spanish, Portuguese, or German) that share an ancestor, and you try to recover that connection.

**Easy** asks you to pick the shared ancestor’s meaning from four choices, then shows the etymology graph. **Hard** gives you the words and asks you to place the ancestors and draw the edges yourself.

Puzzles are built offline from Wiktionary-derived etymology data. The live game never walks that graph: Python ETL writes puzzle rows, a Go API serves one at a time (hiding the answer until you submit), and a React UI plays the round.

Puzzle data is derived from [etymology-db](https://github.com/droher/etymology-db) (CC BY-SA 3.0) plus Wiktionary / kaikki glosses. Attribution belongs in the UI; share-alike still applies to derived puzzles.

## Repository layout

```
etl/            Python CLI: download dumps, filter the graph, emit puzzles
backend/        Go HTTP API + Postgres schema (picks a puzzle, grades a solve)
frontend/       React + Vite UI (home, easy, hard)
data/           Local artifacts (raw dumps, derived graph, puzzle JSONL) — not in git
tests/          ETL tests
docker-compose.yml   Postgres 16 + API
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
| Data | Postgres 16 |

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

Postgres is on `localhost:5432` (`etymoguessr` / `etymoguessr`). To stop the containers: `docker compose down`.
