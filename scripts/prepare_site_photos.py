"""Crops, resizes and compresses the Gemini images for the public site.

The images come from Google Gemini (see scripts/gemini_images.py and
docs/site-images.md), saved as data/gemini/raw/<slot>.png (.jpg, .jpeg or .webp
are fine too). Run from the repo root:

    backend/.venv/Scripts/python scripts/prepare_site_photos.py [folder] [--only SLOT ...]

The folder defaults to data/gemini/raw. Each image is center-cropped to its slot's
shape, resized and saved as WebP in frontend/src/site/img/ under the same name,
where the site picks it up. A slot without a new image keeps its current file
(the Blender render, or the drawing for the scene photos). Uses Pillow, which
the backend already requires.
"""

import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "src" / "site" / "img"
DEFAULT_SOURCE = ROOT / "data" / "gemini" / "raw"

PRODUCTS = [
    "GB-1001", "GB-1002", "GB-1014", "GB-1027", "GB-1033",
    "CH-2004", "CH-2011", "CH-2019", "CH-2026", "CH-2033",
    "finding-rings", "finding-clasp", "finding-wire", "finding-memory",
    "starter-set",
]  # fmt: skip

# slot name: (width, height) of the saved image
SLOTS = {
    "hero-strand": (1200, 900),
    "collection-amber-hollow": (1200, 750),
    "collection-coastal-garden": (1200, 750),
    "story-workshop": (1800, 771),
    **{name: (720, 540) for name in PRODUCTS},
}
EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


def fit(image: Image.Image, width: int, height: int) -> Image.Image:
    """Center-crop to the slot's aspect ratio, then scale down to its size."""
    target = width / height
    w, h = image.size
    if w / h > target:
        new_w = round(h * target)
        left = (w - new_w) // 2
        image = image.crop((left, 0, left + new_w, h))
    else:
        new_h = round(w / target)
        top = (h - new_h) // 2
        image = image.crop((0, top, w, top + new_h))
    return image.resize((width, height), Image.Resampling.LANCZOS)


def find(source: Path, slot: str) -> Path | None:
    for ext in EXTENSIONS:
        if (source / f"{slot}{ext}").is_file():
            return source / f"{slot}{ext}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("folder", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--only", nargs="*", help="slot names to prepare")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    slots = {k: v for k, v in SLOTS.items() if not args.only or k in args.only}
    found = 0
    for slot, (width, height) in slots.items():
        path = find(args.folder, slot)
        if path is None:
            print(f"missing  {slot}  (the site keeps its current image)")
            continue
        with Image.open(path) as image:
            if image.width < width or image.height < height:
                size = f"{image.width}×{image.height}"
                print(f"note     {slot} is {size}, smaller than {width}×{height}")
            picture = fit(image.convert("RGB"), width, height)
        target = OUT / f"{slot}.webp"
        picture.save(target, "WEBP", quality=82, method=6)
        print(f"saved    {target.name}  {target.stat().st_size // 1024} KB")
        found += 1
    print(f"{found} of {len(slots)} slots filled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
