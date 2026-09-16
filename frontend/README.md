# EtymoGuessr frontend

React + TypeScript + Vite UI for EtymoGuessr. Paper/ink design tokens and primitives, plus a non-playable Easy mode shell.

**Not wired yet:** puzzle fetch, solve, or React Flow reveal. Those wait on the Go API.

## Stack

- pnpm
- React 19 + TypeScript + Vite
- CSS variables + CSS Modules (no Tailwind)
- IBM Plex Mono + Serif (`@fontsource`)
- Screen navigation via React state (`home` / `easy` / `hard`) — no react-router

## Scripts

```bash
pnpm install
pnpm dev      # Vite dev server
pnpm build    # typecheck + production build
pnpm lint     # oxlint
pnpm preview  # preview production build
```

## Layout

```
src/
  styles/          # tokens + global CSS
  ui/              # Sheet, IndexCard, PostIt, InkButton, Stamp, Colophon
  features/
    home/          # brand desk + Easy / Hard entry
    easy/          # placeholder two-card + four-post-it shell
    hard/          # coming-soon stub
```

## Design notes

Cream paper desk, graphite ink, low-sat post-its, stamp-red actions. Attribution colophon (CC BY-SA / Wiktionary + etymology-db) on every screen.
