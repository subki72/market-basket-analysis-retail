# Contributing to Market Basket Analysis (Retail)

Thank you for contributing to `market-basket-analysis-retail`. Please follow these engineering standards before opening a pull request.

## Local Development Setup

```bash
python -m venv .venv
# Linux / macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

If using pre-commit hooks:

```bash
pip install pre-commit
pre-commit install
```

## Quality Gates

Every pull request must pass all checks locally and in GitHub Actions:

1. **Lint & Formatting**:
   ```bash
   python -m ruff check src tests main.py
   python -m ruff format --check src tests main.py
   python -m flake8 --max-line-length=120 src tests main.py
   ```
2. **Automated Test Suite**:
   ```bash
   python -m pytest tests/ -v --cov=src --cov-report=term-missing --cov-fail-under=75
   ```
3. **Notebook Preservation**:
   Keep `MBA.ipynb`, `MBA_Results_TopRules.csv`, and `image.png` intact unless explicitly updating notebook analysis outputs.

## Coding & Commit Conventions

- Follow **Conventional Commits** (`feat(api): ...`, `fix(loader): ...`, `test(miner): ...`, `docs(runbook): ...`).
- Keep functions focused (`< 50` lines), shallow (`< 3` nesting levels), and fully type-annotated (`Python 3.11+`).
- Use `logging.getLogger(__name__)` rather than `print()`, handle edge cases with upfront guard clauses, and never swallow exceptions silently.
