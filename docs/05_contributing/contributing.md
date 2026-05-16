# Contributing

Thanks for considering a contribution to the **DatorCloud framework**. This
page is the shortest path from a fresh clone to a passing pull request.

## Repository layout

```
datorcloud/                  # The framework's Python package
  components/                  Five single-responsibility components
  core/                        DatorCloudOrchestrator
  dagster/                     ConfigurableResource + @asset definitions
  cli.py                       datorcloud command entry point
tests/                       pytest suite with FakeMinioClient + fixtures
examples/                    Runnable scripts (basic_usage, dagster_workflow, ...)
docs/                        MkDocs site for the DatorCloud framework
build/                       Dockerfiles for MinIO, DuckDB, Dagster, datorcloud-cli
dataspaces/                  Project storage skeleton (data_lake, data_warehouse, retrieved_data)
workspace.yaml               Dagster workspace pointing at examples/dagster_workflow.py
pyproject.toml               Authoritative project metadata
```

## Local dev setup

```bash
git clone https://github.com/jagh/datorcloud.git
cd datorcloud
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dagster,test,docs]"
```

The `dev` extra also installs `ruff` for linting:

```bash
pip install -e ".[dev]"
```

## Run the tests

```bash
pytest -q                          # full suite
pytest tests/test_orchestrator.py  # one file
pytest -k "retrieve"               # match by name
pytest --cov=datorcloud            # with coverage
```

The Dagster materialization test is auto-skipped when `dagster` is not
installed. CI runs the full matrix on Python 3.10, 3.11, and 3.12.

## Coding conventions

- Extend the framework by adding a new **component** (one class, one
  responsibility) under `datorcloud/components/`, then expose it through the
  orchestrator and, if applicable, as a Dagster asset.
- Use the standard `logging` module. No `print()` in library code.
- Accept collaborators (MinIO client, DuckDB connection, ...) through the
  constructor so tests can inject fakes (see `tests/conftest.py`).
- Type-annotate public functions; the Dagster layer relies on runtime
  annotations, so **never** use `from __future__ import annotations` in
  `datorcloud/dagster/`.
- Run `ruff check datorcloud tests` before pushing.

## Writing tests

- Place new tests under `tests/`, mirroring the module they cover.
- Reuse the shared fixtures:
    - `fake_minio` — in-memory MinIO replacement
    - `minio_component` — `MinioObjectComponent` already wired to the fake
    - `synthetic_dataset` — small dataset tree on disk
- For Dagster assets, use `dagster.materialize([asset], resources=...)`
  with a `DatorCloudResource` that has its MinIO factory monkeypatched —
  see `tests/test_dagster_assets.py`.

## Documentation

The site is built with MkDocs and the `readthedocs` theme:

```bash
pip install -e ".[docs]"
mkdocs serve   # http://localhost:8000
```

Doc pages live under `docs/`, navigation is configured in `mkdocs.yml`.

## Submitting a change

1. Branch from `datorcloud-component` (or `main`, depending on the target).
2. Add or update tests for any behavior change.
3. Run `pytest -q` and `ruff check` locally.
4. Open a pull request describing **what** changed and **why**. CI will run
   tests automatically.

If you are unsure where a change belongs, open a discussion or draft PR — we
would rather hear from you early.
