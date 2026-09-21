# EtymoloGuessr

EtymoloGuessr is a browser game about reconstructing shared word ancestors from etymology data. You are shown modern words that descend from the same source and must solve the connection in one of several modes.

The project builds its puzzle data from two main sources: [etymology-db](https://github.com/droher/etymology-db) for etymology relationships and [Kaikki](https://kaikki.org/) gloss dumps for meanings. The resulting puzzle data remains share-alike and attribution belongs in the UI.

## Data

```mermaid
flowchart LR
    A[etymology-db source data] --> B[ETL]
    C[Kaikki gloss dumps] --> B
    B --> D[JSONL puzzle data]
    B --> E[Postgres puzzle data]
    D --> F[API serves a round at a time]
    E --> F
    F --> G[Frontend plays the game]
```

The ETL pipeline turns the source datasets into a curated puzzle dataset that the app serves to players. The current production snapshot is committed at `backend/internal/catalog/puzzles.jsonl`, so running the ETL is not required to play locally or deploy the existing catalog.

- Etymology relationships: [etymology-db](https://github.com/droher/etymology-db)
- Gloss data: [Kaikki glosses](https://kaikki.org/)

The downloaded source dumps, derived indexes, and scratch puzzle snapshots under `data/` are not committed to the repo. You can download and rebuild them using the ETL if you want to regenerate the catalog (see below). The small ETL fixtures are committed for tests and local pipeline development.

The committed catalog at `backend/internal/catalog/puzzles.jsonl` is the exception: it is the production JSONL snapshot and includes answers (gold graphs and solve payloads). Postgres is runtime state and is not committed. This is an open-data game, not an anti-cheat design: GET routes strip answers for play, and `POST /solve` reveals them by design.

## Project layout

This repo is split into a few main areas:

- `etl/` — data processing and puzzle generation
- `backend/` — API service for serving puzzle data
- `frontend/` — web app UI
- `data/` — generated and raw data artifacts
- `docker-compose.yml` and `docker-compose.test.yml` — local and test stacks

Each layer has its own README for deeper details:

- [etl/README.md](etl/README.md)
- [backend/README.md](backend/README.md)
- [frontend/README.md](frontend/README.md)

## Run locally

The quickest play loop uses the committed catalog and does not need Postgres or the ETL. You need Go 1.24+ and pnpm. Install the frontend dependencies, then run the API and frontend in separate terminals:

```bash
cd backend
go run ./cmd/api
```

```bash
cd frontend
pnpm install
pnpm dev
```

The app is typically available at `http://localhost:5173`; the API uses the embedded catalog at `backend/internal/catalog/puzzles.jsonl` and listens on `http://localhost:8080`.

For DB-backed development or ETL work, install the Python environment and start the Compose database/API instead:

```bash
uv sync
docker compose up --build -d
uv run etl load backend/internal/catalog/puzzles.jsonl
```

Then start the frontend with `pnpm dev` from `frontend/`. Compose exposes Postgres on `localhost:5432` and the API on `localhost:8080`. Compose DB credentials (`etymologuessr:etymologuessr`) are local-dev and test only; production does not use hosted Postgres.

## Tests

Run the project checks in each area:

```bash
uv run pytest -m "not integration"
(cd backend && go test ./...)
(cd frontend && pnpm test)
```

For integration and browser tests, use the test stack:

```bash
docker compose -f docker-compose.test.yml up -d --wait --build
export TEST_DATABASE_URL=postgres://etymologuessr:etymologuessr@localhost:5433/etymologuessr?sslmode=disable
uv run pytest -m integration
(cd backend && TEST_DATABASE_URL=$TEST_DATABASE_URL go test -p 1 ./...)
(cd frontend && pnpm exec playwright install chromium && pnpm test:e2e)
```

The test Compose API is exposed on `http://localhost:18080`; the frontend's Playwright setup uses that URL by default and loads fixture puzzles into the test database.

## Railway deploy

Deploy this as two services, without a Railway Postgres add-on.

1. Deploy the committed snapshot. If the puzzle data has changed, generate a replacement locally and copy it into the API embed before deploying:

```bash
# Only needed when regenerating the catalog:
uv run etl refresh
uv run etl generate --jsonl data/puzzles/puzzles.jsonl
cp data/puzzles/puzzles.jsonl backend/internal/catalog/puzzles.jsonl
```

The API Docker image embeds `backend/internal/catalog/puzzles.jsonl`; Railway does not run the ETL or require Postgres.

2. Create a Railway project with:

- `api` service rooted at `backend`
- `web` service rooted at `frontend`

3. Set the web service build variable `VITE_API_URL` to the public API URL, and set the API service `CORS_ORIGINS` to the public web URL.

4. Deploy the API first, then deploy the web app. The API exposes health checks at `https://<api>/health`, and the frontend serves the SPA routes for the game screens.

## License

Application code is MIT — see [LICENSE](LICENSE). Puzzle data and served puzzle JSON are CC BY-SA 4.0; attribution and source details are in [NOTICE](NOTICE).
