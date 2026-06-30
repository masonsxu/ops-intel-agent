.PHONY: help install dev prod run seed demo clean frontend frontend-install frontend-dev frontend-build test lint format tauri-icons backend-binary tauri-dev tauri-build

help:
	@echo "Ops Intel Agent"
	@echo "  make install          - uv sync (runtime deps; chroma + local LLM, offline-capable)"
	@echo "  make dev / prod       - add dev / prod extras"
	@echo "  make run              - uvicorn API server on :8000"
	@echo "  make frontend         - install + build the Vue UI (served by FastAPI at /)"
	@echo "  make test / lint      - pytest / ruff+mypy"
	@echo ""
	@echo "  Desktop (Tauri):"
	@echo "  make tauri-icons      - regenerate app icons from src-tauri/source-icon.png"
	@echo "  make backend-binary   - compile backend sidecar with Nuitka (→ src-tauri/binaries/)"
	@echo "  make tauri-dev        - run the desktop app (frontend + uv-launched backend)"
	@echo "  make tauri-build      - build distributable desktop bundle (runs backend-binary first)"

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

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

frontend: frontend-install frontend-build

# ── Tauri desktop app ─────────────────────────────────────────────────────────

tauri-icons:
	cargo tauri icon src-tauri/source-icon.png

backend-binary:
	uv run --with nuitka scripts/build_backend.py

tauri-dev:
	cargo tauri dev

tauri-build: backend-binary
	cargo tauri build --release

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
	rm -rf chroma_db
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
