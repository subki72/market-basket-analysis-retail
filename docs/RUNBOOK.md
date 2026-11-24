# Operational Runbook: Market Basket Analysis Service

## 1. Service Overview

`market-basket-analysis-retail` provides both an offline CLI pipeline (`main.py`) and a containerized FastAPI microservice (`src.mba_engine.api:app`) for Apriori association rule mining and cross-sell product recommendations.

## 2. Runtime Configuration

Copy `.env.example` to `.env` for local runs or inject environment variables in container orchestration:

| Variable | Default | Description |
|---|---|---|
| `MBA_MIN_SUPPORT` | `0.02` | Minimum itemset support in `(0.0, 1.0]` |
| `MBA_MIN_CONFIDENCE` | `0.30` | Minimum rule confidence in `[0.0, 1.0]` |
| `MBA_MIN_LIFT` | `1.0` | Minimum rule lift (`>= 0.0`) |
| `MBA_MAX_LEN` | `3` | Maximum itemset length (`2..10`) |
| `MBA_MAX_ITEMS` | `500` | Vocabulary cap before frequency pruning |
| `MBA_DEFAULT_RULES_PATH` | `MBA_Results_TopRules.csv` | Path to cached precomputed top rules |
| `MBA_ALLOWED_ORIGINS` | `http://localhost:3000,http://127.0.0.1:8000` | Comma-separated CORS allowlist |
| `MBA_LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`..`CRITICAL`) |
| `MBA_RATE_LIMIT_PER_MINUTE` | `60` | Per-client sliding-window request limit on `POST /analyze` |

## 3. Startup & Health Verification

### Local CLI Verification
```bash
python main.py --health
```
Expected exit code `0` and JSON output with `"status": "ok"`.

### Containerized API Startup
```bash
docker compose up -d --build
curl -f http://127.0.0.1:8000/health
```
Expected HTTP `200` with `"cached_rules_available": true`.

## 4. Incident & Troubleshooting Playbook

| Symptom | Likely Cause | Diagnostic & Remediation |
|---|---|---|
| `GET /health` shows `cached_rules_available: false` | `MBA_DEFAULT_RULES_PATH` missing or malformed | Verify `MBA_Results_TopRules.csv` is mounted/copied in `/app` and contains valid `frozenset(...)` columns. |
| `POST /analyze` returns `422 Unprocessable Entity` | Empty `baskets`/`transactions` or invalid threshold | Inspect response `detail`; ensure `min_support > 0`, `max_len >= 2`, and non-empty basket inputs. |
| `POST /analyze` returns `429 Too Many Requests` | Client exceeded `MBA_RATE_LIMIT_PER_MINUTE` | Wait up to 60s or tune `MBA_RATE_LIMIT_PER_MINUTE` for trusted internal batch callers. |
| `POST /analyze` returns `rules_count: 0` | Thresholds too strict for submitted basket volume | Lower `min_support` or `min_confidence`; sparse-basket guards intentionally return `[]` instead of failing. |
| `POST /analyze` returns `500` JSON | Unexpected runtime error | Inspect structured logs from `mba_engine`; external clients receive safe generic message without stack traces. |

## 5. Rollback Procedure

1. Revert container deployment to the previous immutable release tag (e.g. `v1.0.0`).
2. Re-run `python main.py --health` and `curl -f http://127.0.0.1:8000/health` to confirm service recovery.
