# Poder Judicial Virtual (pjud)

Second scraper — targets the **Oficina Judicial Virtual** del Poder Judicial.

Layout (mirrors the JPL project's separation):
- `scraper/` — Python backend (scraper + helpers).
- `screenshots/` — dev screenshots (gitignored).
- Frontend SPA lives at `felipe/spa/pjud/` (published to GitHub Pages at `/Felipe/pjud/`).
- GitHub Actions workflows for this scraper live at the repo root `.github/workflows/` (prefix names with `pjud-` to keep them separate from the JPL ones).

The JPL scraper is unchanged: backend at `felipe/scraper/`, frontend at `felipe/spa/jpl/`.
