"""Nuitka compilation entry point for the backend sidecar.

This file lives **outside** the ``ops_intel_agent`` package on purpose. If
Nuitka compiles ``ops_intel_agent/__main__.py`` directly, it treats the
package directory as the source root and flattens sibling modules to the dist
root — in particular our own ``ops_intel_agent/logging.py`` would shadow the
standard-library ``logging`` module, breaking ``import logging`` everywhere.

Compiling this top-level script instead makes ``ops_intel_agent`` a proper
package import, so ``import logging`` resolves to the standard library and our
module stays correctly namespaced as ``ops_intel_agent.logging``.

At runtime (dev) you still run the backend via::

    uv run uvicorn ops_intel_agent.main:app --port 8000
    # or
    uv run python -m ops_intel_agent --port 8000
"""

from ops_intel_agent.__main__ import main

if __name__ == "__main__":
    main()
