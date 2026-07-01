#!/usr/bin/env python3
"""Build the FastAPI backend into a standalone sidecar for the Tauri desktop app.

Uses Nuitka ``--standalone`` to compile the Python backend (entry:
``ops_intel_agent/__main__.py``) plus its native deps (chromadb, onnxruntime,
uvicorn, ...) into a self-contained folder at
``src-tauri/binaries/ops-intel-agent-backend/``. Tauri bundles that folder via
``tauri.conf.json → bundle.resources`` and the Rust shell launches the
executable inside it.

Why ``--standalone`` (folder) by default, not ``--onefile``?
    chromadb pulls in onnxruntime + tokenizers with many native libraries and
    data files. Nuitka ``--onefile`` packs everything into one payload and
    re-extracts it to a temp dir on every launch — slow (seconds) and brittle
    with chromadb's data layout. ``--standalone`` keeps the libs on disk next
    to the binary: faster startup and far more reliable. Pass ``--onefile`` if
    you really want a single file.

Usage
-----
    uv run --with nuitka scripts/build_backend.py             # standalone (default)
    uv run --with nuitka scripts/build_backend.py --onefile   # single binary
    uv run --with nuitka scripts/build_backend.py --debug     # keep build artifacts

Nuitka does NOT cross-compile — run this on each target platform.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PKG = os.path.join(REPO, "ops_intel_agent")
# IMPORTANT: compile the top-level entry script (backend_entry.py), NOT
# ops_intel_agent/__main__.py. Compiling __main__.py directly makes Nuitka
# treat the package dir as the source root, flattening sibling modules
# (notably our logging.py) to the dist root and shadowing the stdlib logging.
ENTRY = os.path.join(REPO, "backend_entry.py")
BUILD_DIR = os.path.join(REPO, "build", "nuitka")
BIN_DIR = os.path.join(REPO, "src-tauri", "binaries")
APP_NAME = "ops-intel-agent-backend"


def _ensure_nuitka() -> None:
    try:
        import nuitka  # type: ignore  # noqa: F401
    except ImportError:
        print(
            "Nuitka not found. Install it first:\n"
            "    uv tool install nuitka\n"
            "  or run via:\n"
            "    uv run --with nuitka scripts/build_backend.py",
            file=sys.stderr,
        )
        sys.exit(1)


def _exe_name() -> str:
    return APP_NAME + (".exe" if platform.system() == "Windows" else "")


_PLACEHOLDER_README = """\
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
"""


def _write_placeholder_readme(folder: str) -> None:
    """Keep a tracked README in the sidecar folder so the resource glob on a
    fresh clone still matches something (the binary itself is gitignored)."""
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "README.md"), "w", encoding="utf-8") as f:
        f.write(_PLACEHOLDER_README)


def _folder_size_mb(path: str) -> float:
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total / (1024 * 1024)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build backend sidecar with Nuitka")
    parser.add_argument("--onefile", action="store_true", help="Single-file binary (default: standalone folder)")
    parser.add_argument("--debug", action="store_true", help="Keep Nuitka build artifacts")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Wipe the Nuitka build cache first (full rebuild). Default keeps the "
        "cache so only changed modules recompile (much faster iteration).",
    )
    args = parser.parse_args()

    _ensure_nuitka()
    os.makedirs(BIN_DIR, exist_ok=True)

    # Remove stale final outputs so we never ship a half-old binary.
    for stale in (os.path.join(BIN_DIR, APP_NAME), os.path.join(BIN_DIR, _exe_name())):
        if os.path.isdir(stale):
            shutil.rmtree(stale)
        elif os.path.exists(stale):
            os.remove(stale)
    if args.clean:
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
    os.makedirs(BUILD_DIR, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        f"--output-dir={BUILD_DIR}",
        # Pydantic v2 has no Nuitka plugin in 4.x; its rust core + schema
        # generation are handled by Nuitka's automatic package support
        # (implicit-imports / anti-bloat core plugins). We force-include
        # the pydantic package below so nothing is tree-shaken away.
        f"--output-filename={_exe_name()}",
        # Our package + the async server entry + heavy native deps. Listing
        # them explicitly avoids Nuitka's static analysis missing dynamic
        # imports inside chromadb/onnxruntime.
        "--include-package=ops_intel_agent",
        "--include-package=pydantic",
        "--include-package=pydantic_core",
        "--include-package=uvicorn",
        "--include-package=chromadb",
        "--include-package=onnxruntime",
        "--include-module=aiosqlite",
        "--include-module=greenlet",
        "--include-module=sqlalchemy.dialects.sqlite",
        # Trim the dev/test-only modules that chromadb's test subpackage and the
        # dev venv drag in — they bloat the binary and slow the C compile while
        # never being needed at runtime.
        "--nofollow-import-to=chromadb.test",
        "--nofollow-import-to=pytest",
        "--nofollow-import-to=mypy",
        "--nofollow-import-to=ruff",
        "--nofollow-import-to=respx",
        ENTRY,
    ]
    # NOTE: Nuitka 4.x removed ``--assume-yes-for-dynamic-glibc`` (it auto-handles
    # the dynamic-glibc case now). Do not pass it — older recipes still mention it.
    if args.onefile:
        cmd.append("--onefile")
    if args.debug:
        cmd.append("--debug")
    else:
        cmd.append("--remove-output")

    print("Running Nuitka:")
    print("  " + " ".join(cmd))
    sys.stdout.flush()
    subprocess.run(cmd, cwd=REPO, check=True)

    # Post-process: Nuitka emits build/nuitka/<entry-stem>.dist/ (standalone) or
    # build/nuitka/<exe> (onefile). Relocate/rename to the layout the Rust side
    # expects: binaries/ops-intel-agent-backend/<exe>.  Both modes land the exe
    # inside the ``ops-intel-agent-backend`` folder so the Rust path resolution
    # (resource_dir/binaries/ops-intel-agent-backend/<exe>) and the Tauri
    # resources glob (binaries/ops-intel-agent-backend/**/*) work identically.
    exe = _exe_name()
    entry_stem = os.path.splitext(os.path.basename(ENTRY))[0]
    dest_dist = os.path.join(BIN_DIR, APP_NAME)
    if args.onefile:
        produced = os.path.join(BUILD_DIR, exe)
        if not os.path.exists(produced):
            print(f"ERROR: onefile binary not found at {produced}", file=sys.stderr)
            sys.exit(1)
        os.makedirs(dest_dist, exist_ok=True)
        dest = os.path.join(dest_dist, exe)
        shutil.move(produced, dest)
        size_root = dest
    else:
        produced_dist = os.path.join(BUILD_DIR, f"{entry_stem}.dist")
        if not os.path.isdir(produced_dist):
            print(f"ERROR: standalone dist folder not found at {produced_dist}", file=sys.stderr)
            sys.exit(1)
        if os.path.exists(dest_dist):
            shutil.rmtree(dest_dist)
        shutil.move(produced_dist, dest_dist)
        dest = os.path.join(dest_dist, exe)
        if not os.path.exists(dest):
            print(f"ERROR: expected executable not found at {dest}", file=sys.stderr)
            sys.exit(1)
        size_root = dest_dist

    if platform.system() != "Windows":
        st = os.stat(dest)
        os.chmod(dest, st.st_mode | 0o755)

    # Recreate the placeholder README so the folder always has a tracked file
    # (the binary itself is gitignored). This keeps `git status` clean after a
    # build and ensures the resource glob resolves on a fresh clone where the
    # binary hasn't been compiled yet.
    _write_placeholder_readme(dest_dist)

    print(f"\n✅ Sidecar ready:")
    print(f"   binary : {dest}")
    print(f"   size   : ~{_folder_size_mb(size_root):.0f} MB")
    print(f"   next   : cargo tauri build   (bundles this via bundle.resources)")


if __name__ == "__main__":
    main()
