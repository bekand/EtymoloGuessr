# Security Policy

## Supported surfaces

EtymoloGuessr exposes an unauthenticated public API by design. The intended routes are:

- `GET /health`
- `GET /puzzles/*` (prompts without answers)
- `POST /solve` (reveals answers for a played round)

There is no authentication, admin surface, or privileged API.

## Reporting a vulnerability

Please report security issues privately by opening a GitHub security advisory on this repository, or by emailing the maintainer listed on the GitHub profile for this project.

Do not open a public issue for vulnerabilities that could be exploited before a fix is available.

Include a short description of the issue, steps to reproduce, and any impact you have assessed. We will acknowledge reports as soon as practical and coordinate disclosure after a fix is ready.
