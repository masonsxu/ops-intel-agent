"""CLI entry point for the bundled backend binary.

The Tauri shell launches the Nuitka-compiled binary
``ops-intel-agent-backend`` with ``--host`` / ``--port`` flags. In development
the backend is instead started via ``uv run uvicorn ops_intel_agent.main:app``.

    python -m ops_intel_agent --port 8000

Uses **absolute** imports so it works both as ``python -m ops_intel_agent``
(package context present) and as a Nuitka-compiled entry (no package context
on ``__main__``).
"""

from __future__ import annotations

# Import the stdlib ``logging`` module before anything that might touch it
# indirectly (structlog, asyncio). Harmless in dev; in the Nuitka-built binary
# it ensures logging is fully initialised early.
import logging  # noqa: E402

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ops-intel-agent-backend",
        description="Run the Ops Intel Agent FastAPI server.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    args = parser.parse_args()

    # Imported lazily so argparse stays fast and the binary starts quickly.
    import uvicorn

    from ops_intel_agent.config import get_settings

    settings = get_settings()
    uvicorn.run(
        "ops_intel_agent.main:app",
        host=args.host,
        port=args.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
