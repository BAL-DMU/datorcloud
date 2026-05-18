# DatorCloud Framework — Documentation

This folder contains the source for the **DatorCloud framework**'s MkDocs
site. When browsing on GitHub, use the links below; when running the site
locally, see [Building locally](#building-locally).

## Map of the docs

| Section                                                       | What it covers                                                       |
| :------------------------------------------------------------ | :------------------------------------------------------------------- |
| [Overview](01_overview/overview.md)                           | What DatorCloud is, how it complements **BAL-JH Spaces**, and where it sits in the institutional **Trusted Research Environment (TRE)**. |
| [Installation](02_installation/installing_core_data_platform.md) | Bring up the MinIO + DuckDB + Dagster stack with Docker Compose; `.env`-driven configuration. |
| [Component Architecture](03_components/architecture.md)       | L1–L4 data model, three storage tiers, five components, and the `DatorCloudOrchestrator` (with the new `from_env()` factory). |
| [Quickstart](04_user_guide/quickstart.md)                     | Fresh clone → working pipeline in five minutes.                      |
| [Tutorial — 4dor-dataset](04_user_guide/tutorial_4dor.md)     | End-to-end walkthrough on the bundled multi-camera surgical dataset. |
| [Python API](04_user_guide/python_api.md)                     | Orchestrator + individual component reference.                       |
| [CLI](04_user_guide/cli.md)                                   | `datorcloud upload / metadata / query / retrieve / version`.         |
| [Dagster Integration](04_user_guide/dagster.md)               | `DatorCloudResource` and the four chained `@asset`s.                 |
| [Contributing](05_contributing/contributing.md)               | Local dev setup, test conventions, doc workflow.                     |

## Building locally

The site is built with **MkDocs** using the `readthedocs` theme. From the
project root:

```bash
pip install -e ".[docs]"      # installs mkdocs + plantuml-markdown + pymdown-extensions
mkdocs serve                  # http://localhost:8000 — live reload
mkdocs build --strict         # one-shot build into ./site/
```

`mkdocs build --strict` is what the CI uses; failures there block merge.

## Navigation & assets

- The site map is defined in `mkdocs.yml` at the repo root (`nav:` block).
- Brand assets live under `docs/assets/`: `datorcloud-logo.png` (sidebar
  wordmark), `datorcloud-icon.png` (transparent HD icon), and
  `datorcloud-name.png`. The browser-tab favicon is generated from the icon
  and lives at `docs/favicon.ico`.
- Sidebar branding is wired through `theme.logo` and `theme.favicon` in
  `mkdocs.yml`; the burgundy logo/search header comes from
  `docs/stylesheets/extra.css`.

## Deployment

The repo is set up to publish via GitHub Pages with:

```bash
mkdocs gh-deploy
```

This builds the site and pushes it to the `gh-pages` branch. Live URL is
configured in the institutional Trusted Research Environment.

## Writing conventions

- Every Python and YAML snippet must read credentials from `.env` — no
  hard-coded values, no `minioadmin` literals. Use
  `DatorCloudOrchestrator.from_env()` for the orchestrator and
  `os.environ[...]` for individual components.
- CLI examples must label the execution context with the conventional
  prefix: `host$` (host shell), `cli#` (inside the `datorcloud-cli`
  container), `runner#` (inside `python-runner`).
- Image and asset references inside MkDocs pages use **Markdown image
  syntax** (`![alt](../assets/foo.png)`), not raw `<img>` tags, so MkDocs
  rewrites the paths correctly under directory-style URLs.
