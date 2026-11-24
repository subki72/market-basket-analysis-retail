.PHONY: install lint format test cli serve docker-build clean

PYTHON ?= python

install:
	$(PYTHON) -m pip install -r requirements.txt

lint:
	$(PYTHON) -m ruff check src tests main.py
	$(PYTHON) -m flake8 --max-line-length=120 src tests main.py

format:
	$(PYTHON) -m ruff format src tests main.py

test:
	$(PYTHON) -m pytest tests/ -v --cov=src --cov-report=term-missing

cli:
	$(PYTHON) main.py --health

serve:
	uvicorn src.mba_engine.api:app --host 0.0.0.0 --port 8000 --reload

docker-build:
	docker build -t market-basket-analysis-retail:latest .

clean:
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in [*pathlib.Path('.').rglob('__pycache__'), pathlib.Path('.pytest_cache'), pathlib.Path('.ruff_cache'), pathlib.Path('outputs')]]; pathlib.Path('.coverage').unlink(missing_ok=True)"
