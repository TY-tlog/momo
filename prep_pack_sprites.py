"""사진 한 장에서 3마리(요키/진돗개/비숑)를 각각 잘라
assets/dog_yorkie.png, dog_jindo.png, dog_bichon.png 로 저장.

Usage:
    python prep_pack_sprites.py <input_image>
"""
from __future__ import annotations

import sys
from pathlib import Path

ASSET_DIR = Path(__file__).parent / "assets"

# 원본 이미지(960x768) 기준 대략적 좌우 영역. 넉넉히 겹쳐 잡아서
# rembg 가 각 강아지를 깔끔히 분리하도록 한다.
# (left, top, right, bottom) — 비율로 저장해서 다른 해상도에도 대응
CROPS = {
    "yorkie": (0.00, 0.25, 0.40, 1.00),
    "jindo":  (0.36, 0.00, 0.66, 1.00),
    "bichon": (0.64, 0.25, 1.00, 1.00),
}


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python prep_pack_sprites.py <input_image>")
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
    W, H = img.size

    for name, (l, t, r, b) in CROPS.items():
        box = (int(l * W), int(t * H), int(r * W), int(b * H))
        print(f"[{name}] crop {box}")
        crop = img.crop(box)
        print(f"[{name}] removing background ...")
        out = remove(crop)
        bbox = out.getbbox()
        if bbox:
            out = out.crop(bbox)
        out_path = ASSET_DIR / f"dog_{name}.png"
        out.save(out_path)
        print(f"[{name}] saved {out_path}  ({out.size[0]}x{out.size[1]})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
