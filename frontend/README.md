# EtymoGuessr frontend

React + TypeScript + Vite UI for EtymoGuessr. Paper/ink design tokens, primitives, a playable Easy mode, and a Hard stub.

Easy talks to the Go API: random prompt, submit a meaning, then a read-only etymology graph. Hard is still a coming-soon screen.

## Stack

- pnpm
- React 19 + TypeScript + Vite
- Sass (SCSS) + CSS variables (no Tailwind)
- IBM Plex Mono + Serif (`@fontsource`)
- TanStack Query for puzzle fetch / solve
- React Flow (`@xyflow/react`) for the post-submit graph
- Screen navigation via React state (`home` / `easy` / `hard`) — no react-router

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
  api/             # fetch helper, puzzle types, random/solve + easy lock
  query/           # QueryClient
  styles/          # tokens + global Sass
  utils/           # seeded shuffle (choice order + post-it colors)
  ui/              # Sheet, IndexCard, PostIt, InkButton, Stamp, Colophon
    graph/         # read-only EtymologyGraph (custom nodes + ink edges)
  features/
    home/          # Home sheet + Easy / Hard entry
    easy/          # live MC puzzle + graph reveal
    hard/          # coming-soon stub
```

## Easy mode

1. `GET /puzzles/random?mode=easy` — two index cards, four meaning post-its.
2. The current prompt is locked in `localStorage` so refresh does not swap the puzzle.
3. Choice order and post-it colors are shuffled from the first digit in the puzzle id.
4. `POST /puzzles/{id}/solve` — cards and post-its hide; verdict + `goldGraph` (React Flow, relation labels on edges).
5. Next clears the lock and fetches another prompt.

## Design notes

Light paper sheets, darker ink, low-sat post-its, rectangular stamp actions. Attribution colophon (CC BY-SA / Wiktionary + etymology-db) on every screen. Hard entry is disabled until that mode ships.
