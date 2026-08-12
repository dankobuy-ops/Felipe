# Felipe

Scrapers and the tools around them.

## 📖 [The Scraper's Handbook](SCRAPERS_HANDBOOK.md) — read this first

Everything these projects have learned about making scrapers work, drawn from all of them.
**Read it before building a new scraper, and update it when a build teaches you something.**

Its first rule is the one that matters most:

> **A scraper must not do anything a human could not do, or would not do.**

## Projects

| project | what it scrapes | docs |
|---|---|---|
| `felipe/pjud/` | Oficina Judicial Virtual — civil causas with a bank plaintiff → Neon + Drive | `felipe/pjud/README.md` |
| `felipe/scraper/` | Juzgados de Policía Local (JPL) → Sheets + Drive; plate enrichment | — |
| `cias/HDI-Ruts-Scraper/` | HDI broker cotizador — contact details by RUT → Sheets | `cias/HDI-Ruts-Scraper/README.md` |
| `felipe/spa/` | the front ends, published to GitHub Pages | — |
| `pdf-extractor/`, `webcam/` | offline OCR / plate recognition | — |

Workflows live at `.github/workflows/`, prefixed by project.
