# Market Basket Analysis (MBA) for Retail

Production-hardened **Market Basket Analysis** pipeline and **FastAPI microservice** built around the **Apriori algorithm** (`mlxtend`), preserving the original exploratory analysis notebook (`MBA.ipynb`), precomputed top rules (`MBA_Results_TopRules.csv`), and visualization (`image.png`) untouched.

## Key Business Insights Discovered

From association rule mining on retail transactions (`min_support=0.02`, `min_lift=1.0`), key cross-sell patterns include:

1. **Variant Collectors (High Lift Co-Purchase)**: Customers purchasing the *Sweetheart Ceramic Trinket Box* show a **75.8% confidence** of also purchasing the *Strawberry Ceramic Trinket Box* (**Lift: 11.21**).
   - **Action**: Co-locate variant SKUs on merchandising pages and trigger checkout cross-sell prompts.
2. **Set Builders**: Customers purchasing *Wooden Picture Frame White Finish* buy *Wooden Frame Antique White* at **68.3% confidence** (**Lift: 12.39**), and *Heart of Wicker Small* leads to *Heart of Wicker Large* at **56.1% confidence** (**Lift: 9.12**).
   - **Action**: Offer curated multi-size or matching-theme bundle discounts to lift Average Order Value (AOV).

## Architecture Overview

This repository follows a dual-mode non-breaking architecture:

- **Exploratory Artifact (Preserved)**: `MBA.ipynb`, `MBA_Results_TopRules.csv`, and `image.png`.
- **Modular Python Engine (`src/mba_engine/`)**:
  - `config.py`: Validated `MBAConfig` environment loader (`.env.example`) and structured leveled logger (`logging.getLogger(__name__)`).
  - `schemas.py`: Strict Pydantic v2 contracts for transactions, basket requests, ranked rules, and cross-sell recommendations.
  - `loader.py`: CSV reader with UTF-8/ISO-8859-1 fallback, cancellation/noise filtering, modal `product_code` standardization, deterministic synthetic sample generator, and mtime-aware cached rule loader.
  - `miner.py`: Typed `TransactionEncoder`, `apriori`, and `association_rules` pipeline with sparse-basket guards, cross-sell recommender, and headless `Agg` scatter exporter.
  - `api.py`: FastAPI microservice (`GET /health`, `GET /rules/top`, `POST /analyze`) with `CORSMiddleware`, defensive security headers, sliding-window rate limiting, and global exception handling.
- **CLI Entrypoint (`main.py`)**: Headless batch execution for CSV datasets, precomputed rules, synthetic samples, and `--health` diagnostics.

## Tech Stack

- **Language & ML**: Python 3.11+, Pandas, NumPy, MLxtend (`TransactionEncoder`, `apriori`, `association_rules`), Matplotlib, Seaborn
- **API & Validation**: FastAPI, Uvicorn, Pydantic v2, HTTPX
- **Quality & Ops**: Ruff, Flake8, Pytest + Coverage, Pre-commit, Docker (multi-stage non-root), GitHub Actions (Semgrep SAST + Trivy)

## Quickstart

### 1. Local Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1 | Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Using Makefile

```bash
make lint          # Run Ruff & Flake8 checks
make test          # Run Pytest suite with coverage report
make cli           # Run CLI health diagnostics
make serve         # Start FastAPI server on http://127.0.0.1:8000
make docker-build  # Build non-root multi-stage container image
```

### 3. CLI Usage Examples

```bash
# Verify configuration and cached rules readiness
python main.py --health

# Inspect top cached rules and get cross-sell recommendations
python main.py --rules-csv MBA_Results_TopRules.csv --top-n 5 --recommend "sweetheart ceramic trinket box"

# Run Apriori mining on synthetic sample baskets or your own retail CSV
python main.py --sample-baskets 120 --min-support 0.05 --min-confidence 0.40
python main.py --input "Online Retail Data.csv" --rules-csv outputs/rules.csv --plot-output outputs/mba.png
```

### 4. FastAPI Microservice

Start the API server:

```bash
uvicorn src.mba_engine.api:app --host 0.0.0.0 --port 8000
```

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | `GET` | Liveness and cached rules readiness probe |
| `/rules/top?limit=20` | `GET` | Return precomputed top rules from `MBA_Results_TopRules.csv` |
| `/analyze` | `POST` | Mine live association rules and cross-sell recommendations from baskets or line items |

Example `POST /analyze` payload:

```json
{
  "baskets": [
    ["sweetheart ceramic trinket box", "strawberry ceramic trinket box"],
    ["sweetheart ceramic trinket box", "strawberry ceramic trinket box"],
    ["heart of wicker small", "heart of wicker large"]
  ],
  "min_support": 0.25,
  "min_confidence": 0.5,
  "min_lift": 1.0,
  "recommend_for": ["sweetheart ceramic trinket box"]
}
```

### 5. Docker Compose

```bash
docker compose up -d --build
curl http://127.0.0.1:8000/health
```

## Visualization

The scatter plot below maps discovered rules by Support (popularity), Confidence (co-purchase probability), and Lift (association strength):

![MBA Scatter Plot](image.png)

## Governance & Documentation

- Security Policy: [SECURITY.md](SECURITY.md)
- Contributing Guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Release History: [CHANGELOG.md](CHANGELOG.md)
- Operations Runbook: [docs/RUNBOOK.md](docs/RUNBOOK.md)
- License: [LICENSE](LICENSE) (MIT)
