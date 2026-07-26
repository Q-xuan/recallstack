.PHONY: install dev test lint format frontend-build migrate

install:
	python -m pip install -e ".[web,dev]"
	cd frontend && npm install

dev:
	@echo "Run backend: python -m recallstack.cli serve --port 8000"
	@echo "Run frontend: cd frontend && npm run dev"

test:
	python -m pytest -q

lint:
	python -m ruff check src tests
	cd frontend && npx tsc --noEmit

format:
	python -m ruff check --fix src tests

frontend-build:
	cd frontend && npm run build

migrate:
	alembic upgrade head
