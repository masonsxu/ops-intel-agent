.PHONY: help install dev run test lint format migrate seed demo clean

help:
	@echo "Ops Intel Agent"
	@echo "  make install   - install runtime deps (offline-capable)"
	@echo "  make dev       - install runtime + dev deps"
	@echo "  make prod      - install runtime + production backends (openai/pgvector)"
	@echo "  make run       - run the API server (offline mode)"
	@echo "  make seed      - seed demo knowledge base"
	@echo "  make demo      - seed + fire a sample alert"
	@echo "  make test      - run the test suite"
	@echo "  make lint      - ruff + mypy"

install:
	uv sync

dev:
	uv sync --extra dev

prod:
	uv sync --extra prod

run:
	uv run uvicorn ops_intel_agent.main:app --reload --host 0.0.0.0 --port 8000

seed:
	uv run python scripts/seed_demo.py

demo:
	uv run python scripts/seed_demo.py
	uv run python scripts/fire_demo_alert.py

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy ops_intel_agent || true

format:
	uv run ruff format .
	uv run ruff check --fix .

clean:
	rm -f *.db *.db-journal
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
