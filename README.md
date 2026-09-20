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

The ETL pipeline turns the source datasets into a curated puzzle dataset that the app serves to players.

- Etymology relationships: [etymology-db](https://github.com/droher/etymology-db)
- Gloss data: [Kaikki glosses](https://kaikki.org/)

These are not committed to the repo, but you can download them using the ETL if you want real data (see below).

The committed catalog at `backend/internal/catalog/puzzles.jsonl` includes answers (gold graphs and solve payloads). This is an open-data game, not an anti-cheat design: GET routes strip answers for play, and `POST /solve` reveals them by design.

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

From the repo root:

```bash
uv sync
docker compose up --build -d
```

Then load the bundled fixture data and start the web app:

```bash
uv run etl reset --all --reload --fixtures
cd frontend
pnpm install
pnpm dev
```

The app is typically available at `http://localhost:5173`. The API is served on `http://localhost:8080`, and the local Postgres instance is on `localhost:5432`. Compose DB credentials (`etymologuessr:etymologuessr`) are local-dev and test only; production does not use hosted Postgres.

## Tests

Run the project checks in each area:

```bash
uv run pytest -m "not integration"
cd backend && go test ./...
cd frontend && pnpm test
```

For integration and browser tests, use the test stack:

```bash
docker compose -f docker-compose.test.yml up -d --wait --build
export TEST_DATABASE_URL=postgres://etymologuessr:etymologuessr@localhost:5433/etymologuessr?sslmode=disable
uv run pytest -m integration
cd backend && TEST_DATABASE_URL=$TEST_DATABASE_URL go test -p 1 ./...
cd frontend && pnpm exec playwright install chromium && pnpm test:e2e
```

## Railway deploy

Deploy this as two services, without a Railway Postgres add-on.

1. Generate a fresh puzzle snapshot locally and copy it into the API embed:

```bash
uv run etl refresh
uv run etl generate --jsonl data/puzzles/puzzles.jsonl
cp data/puzzles/puzzles.jsonl backend/internal/catalog/puzzles.jsonl
```

2. Create a Railway project with:

- `api` service rooted at `backend`
- `web` service rooted at `frontend`

3. Set the web service build variable `VITE_API_URL` to the public API URL, and set the API service `CORS_ORIGINS` to the public web URL.

4. Deploy the API first, then deploy the web app. The API exposes health checks at `https://<api>/health`, and the frontend serves the SPA routes for the game screens.

## License

Application code is MIT — see [LICENSE](LICENSE). Puzzle data and served puzzle JSON are CC BY-SA 4.0; attribution and source details are in [NOTICE](NOTICE).
