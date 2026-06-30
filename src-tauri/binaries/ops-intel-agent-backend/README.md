# Backend sidecar (Nuitka output)

This folder holds the Nuitka `--standalone` build of the Python backend:
the executable `ops-intel-agent-backend` plus its bundled native libraries
(chromadb, onnxruntime, ...). Tauri bundles the whole folder via
`tauri.conf.json -> bundle.resources` and the Rust shell launches the
executable inside it.

Build it with:

    make backend-binary      # uv run --with nuitka scripts/build_backend.py

The binary artifacts here are gitignored (see `src-tauri/.gitignore`); only
this README is committed so the Tauri resource glob always resolves — even on
a fresh clone before the sidecar has been compiled.
