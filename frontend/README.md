# EtymoGuessr frontend

React + TypeScript + Vite UI for EtymoGuessr. Paper/ink design tokens and primitives, plus a non-playable Easy mode shell.

**Not wired yet:** puzzle fetch, solve, or React Flow reveal. Those wait on the Go API.

## Stack

- pnpm
- React 19 + TypeScript + Vite
- Sass (SCSS) + CSS variables (no Tailwind)
- IBM Plex Mono + Serif (`@fontsource`)
- Screen navigation via React state (`home` / `easy` / `hard`) — no react-router

## Scripts

```bash
pnpm install
pnpm dev      # Vite dev server
pnpm build    # typecheck + production build
pnpm lint     # eslint
pnpm preview  # preview production build
```

## Layout

```
src/
  styles/          # tokens + global Sass
  ui/              # Sheet, IndexCard, PostIt, InkButton, Stamp, Colophon
  features/
    home/          # Home sheet + Easy / Hard entry
    easy/          # placeholder two-card + four-post-it shell
    hard/          # coming-soon stub
```

## Design notes

Light paper sheets, darker ink, low-sat post-its, rectangular stamp actions. Attribution colophon (CC BY-SA / Wiktionary + etymology-db) on every screen. Hard entry is disabled until that mode ships.
