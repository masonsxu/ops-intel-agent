#!/usr/bin/env python3
"""Generate Tauri app icons from a source PNG.

Requires Pillow::

    uv run --with Pillow scripts/generate_icons.py <source_1024.png>

Places all required icon sizes into ``src-tauri/icons/``.
"""

from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(HERE, "..", "src-tauri", "icons")

REQUIRED = {
    "32x32.png": 32,
    "128x128.png": 128,
    "128x128@2x.png": 256,
    "icon.png": 512,
    "icon.ico": (32, 32),  # Windows ICO
    "icon.icns": (1024, 1024),  # macOS ICNS
    "Square30x30Logo.png": 30,
    "Square44x44Logo.png": 44,
    "Square71x71Logo.png": 71,
    "Square89x89Logo.png": 89,
    "Square107x107Logo.png": 107,
    "Square142x142Logo.png": 142,
    "Square150x150Logo.png": 150,
    "Square284x284Logo.png": 284,
    "Square310x310Logo.png": 310,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Tauri icons")
    parser.add_argument("source", help="Source PNG (at least 1024x1024)")
    args = parser.parse_args()

    if not os.path.exists(args.source):
        print(f"❌ Source not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    from PIL import Image

    img = Image.open(args.source).convert("RGBA")
    os.makedirs(ICON_DIR, exist_ok=True)

    for name, size in REQUIRED.items():
        if isinstance(size, tuple):
            resized = img.resize(size, Image.LANCZOS)
        else:
            resized = img.resize((size, size), Image.LANCZOS)
        path = os.path.join(ICON_DIR, name)
        resized.save(path)
        print(f"  {path}  ({size})")

    print(f"\n✅ {len(REQUIRED)} icons written to {ICON_DIR}")


if __name__ == "__main__":
    main()
