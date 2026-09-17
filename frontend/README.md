# EtymoGuessr frontend

React + TypeScript + Vite UI for EtymoGuessr. Paper/ink design tokens, primitives, and playable Easy and Hard modes on React Router (`/`, `/easy`, `/hard`).

Easy is two modern words and a four-way meaning choice; Hard is a graph editor. Both talk to the Go API, then share a read-only etymology graph after submit.

## Stack

- pnpm
- React 19 + TypeScript + Vite
- Sass (SCSS) + CSS variables (no Tailwind)
- IBM Plex Mono + Serif (`@fontsource`)
- TanStack Query for puzzle fetch / solve
- React Flow (`@xyflow/react`) for the Hard blotter and the post-submit graph
- React Router (`/`, `/easy`, `/hard`)

## Scripts

```bash
pnpm install
pnpm dev      # Vite dev server (proxies /api → Go on :8080)
pnpm build    # typecheck + production build
pnpm lint     # eslint
pnpm preview  # preview production build
pnpm test     # Vitest (unit + MSW)
pnpm test:e2e # Playwright against the test API (see root README)
```

Dev expects the API at `http://localhost:8080`. The client calls `/puzzles/...`; Vite exposes that as `/api/puzzles/...` and strips `/api` before forwarding. Override with `VITE_API_URL` (no `/api` suffix), e.g. `http://localhost:8080`.

## Tests

`pnpm test` runs Vitest (shuffle/layout units, puzzle-lock + EasyMode with MSW). `pnpm test:e2e` runs Playwright Easy and Hard journeys against `docker-compose.test.yml` (see the root README). Install the browser once with `pnpm exec playwright install chromium`.

## Layout

```
src/
  api/             # fetch helper, puzzle types, random/by-id/solve + per-mode lock
  query/           # QueryClient
  styles/          # tokens + global Sass
  utils/           # seeded shuffle (choice order + post-it colors)
  ui/              # Sheet, IndexCard, PostIt, InkButton, Stamp, Colophon
    graph/         # EtymologyGraph, EtymologyNode, InkEdge
  features/
    home/          # Home sheet + Easy / Hard stamps
    easy/          # live MC puzzle + graph reveal
    hard/          # HardMode + HardCanvas (palette, place, connect)
    feedback/      # shared verdict + gold graph
```

## Easy mode

1. `GET /puzzles/random?mode=easy` — two index cards, four meaning post-its. Index cards have an Explain control for the leaf gloss.
2. The current prompt is locked in `localStorage` so refresh does not swap the puzzle. On reload the client re-fetches `GET /puzzles/{id}?mode=easy`; **404** clears the lock (the row may be gone after `generate --db`).
3. Choice order and post-it colors are shuffled from the puzzle id.
4. `POST /puzzles/{id}/solve` — cards and post-its hide; `FeedbackScreen` shows the verdict + `goldGraph` (React Flow, relation labels on edges).
5. Next clears the lock and fetches another prompt.

## Hard mode

1. `GET /puzzles/random?mode=hard` — only puzzles with **≥ 4 graph nodes**. `promptGraph` has every gold node (glosses kept), `edges: []`. Terms stay so known ancestor cards can be placed. The UI ignores `choices`.
2. Same per-mode `localStorage` lock as Easy: reload re-fetches `GET /puzzles/{id}?mode=hard`; **404** clears the lock.
3. **No nodes start on the blotter** — leaves and ancestors sit in a post-it palette. Place every card (click or drag), then draw directed edges **child → ancestor**. Player edges have no relation-type labels.
4. Submit is disabled until every node is placed (hint: “Build the graph!”). Score is an exact directed edge-set match (ignore order and `reltype`).
5. After submit, the same `FeedbackScreen` as Easy: verdict + read-only gold graph with relation labels.

## Design notes

Light paper sheets, darker ink, low-sat post-its, rectangular stamp actions. No dark theme. Language is an ink stamp on a card (`EN`, `DE`), not a color-coded rainbow. Attribution colophon (CC BY-SA / Wiktionary + etymology-db) on every screen. Home Easy / Hard stamps are both live.
