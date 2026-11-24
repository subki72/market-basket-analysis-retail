# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-24

### Added
- Modular Python package `src/mba_engine/` while keeping original `MBA.ipynb`, `MBA_Results_TopRules.csv`, and `image.png` intact:
  - `src/mba_engine/config.py`: Validated `MBAConfig` environment loader and structured leveled logging (`configure_logging`).
  - `src/mba_engine/schemas.py`: Pydantic v2 contracts (`TransactionLine`, `BasketAnalysisRequest`, `AssociationRuleItem`, `RecommendationItem`, `BasketAnalysisResponse`, `HealthResponse`).
  - `src/mba_engine/loader.py`: Retail CSV reader with UTF-8/ISO-8859-1 fallback, cancellation/noise cleaning, modal `product_code` standardization, deterministic synthetic basket generator, and mtime-aware cached rule loader (`ast.literal_eval`).
  - `src/mba_engine/miner.py`: Typed `TransactionEncoder`, `apriori`, and `association_rules` wrapper with sparse-basket guards, finite-metric sanitization, cross-sell recommender, and headless `Agg` scatter plotter.
  - `src/mba_engine/api.py`: FastAPI microservice (`GET /health`, `GET /rules/top`, `POST /analyze`) with `CORSMiddleware`, defensive security headers, sliding-window rate limiter, and global exception handler.
- CLI runner `main.py` supporting `--health`, `--input`, `--rules-csv`, `--recommend`, and `--plot-output`.
- 5 offline Pytest suites (`tests/test_loader.py`, `tests/test_miner.py`, `tests/test_schemas_and_config.py`, `tests/test_cli.py`, `tests/test_api_integration.py`).
- Pinned dependency manifests (`requirements.txt`, `requirements-lock.txt`, `uv.lock`), `pyproject.toml`, `.flake8`, `.pre-commit-config.yaml`, `Makefile`, multi-stage non-root `Dockerfile`, and `docker-compose.yml`.
- GitHub Actions CI pipeline (`.github/workflows/ci.yml`), Dependabot configuration (`.github/dependabot.yml`), `SECURITY.md`, `CONTRIBUTING.md`, and `docs/RUNBOOK.md`.
