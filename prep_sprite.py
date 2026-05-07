"""Prepare the dog sprite from a raw photo.

원본 사진에서 배경을 제거하고 (rembg 사용) 가장자리 공백을 잘라내서
assets/dog.png 로 저장한다. 한 번만 실행하면 됨.

Usage:
    python prep_sprite.py <input_image>
"""
from __future__ import annotations

import sys
from pathlib import Path

ASSET_DIR = Path(__file__).parent / "assets"
OUTPUT = ASSET_DIR / "dog.png"


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python prep_sprite.py <input_image>")
        return 1

    src = Path(sys.argv[1]).expanduser()
    if not src.exists():
        print(f"Not found: {src}")
        return 1

    ASSET_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from rembg import remove
        from PIL import Image
    except ImportError as e:
        print(f"Missing dependency: {e}. Run: pip install rembg Pillow")
        return 1

    print(f"Loading {src.name} ...")
    img = Image.open(src).convert("RGBA")

    print("Removing background (first run downloads ~170MB model) ...")
    out = remove(img)

    bbox = out.getbbox()
    if bbox:
        out = out.crop(bbox)

    out.save(OUTPUT)
    print(f"Saved: {OUTPUT}  ({out.size[0]}x{out.size[1]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
