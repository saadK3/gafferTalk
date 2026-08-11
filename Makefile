.PHONY: install dev-api dev-web lint test typecheck check

PYTHON ?= python3
PNPM ?= pnpm

install:
	$(PNPM) install --frozen-lockfile
	$(PYTHON) -m pip install -e './apps/api[dev]'

dev-api:
	$(PYTHON) -m uvicorn gaffertalk_api.main:app --app-dir apps/api/src --reload

dev-web:
	$(PNPM) dev:web

lint:
	$(PNPM) lint:web
	$(PYTHON) -m ruff check apps/api
	$(PYTHON) -m ruff format --check apps/api

typecheck:
	$(PNPM) typecheck:web
	$(PYTHON) -m mypy apps/api/src

test:
	$(PYTHON) -m pytest apps/api/tests

check: lint typecheck test
