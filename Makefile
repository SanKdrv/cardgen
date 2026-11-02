.PHONY: install lint fmt type test test-all smoke run demo check

install:
	python -m pip install -e ".[dev]"
	pre-commit install
	pre-commit install --hook-type commit-msg
	pre-commit install --hook-type pre-push

lint:
	ruff check .
	ruff format --check .

fmt:
	ruff check --fix .
	ruff format .

type:
	mypy src

test:
	pytest -m "not smoke"

test-all:
	pytest

smoke:
	pytest -m smoke

coverage:
	pytest -m "not smoke" --cov=cardgen --cov-report=term-missing

run:
	uvicorn cardgen.api:app --reload --port 8000

demo:
	cardgen generate --input examples/products.json --output examples/output --overwrite

check: lint type test
