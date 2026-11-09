"""Crops, resizes and compresses the AI-generated scene photos for the public site.

Put the images you generated in any folder, named after their slot (any of
.png, .jpg, .jpeg or .webp), then run from the repo root:

    backend/.venv/Scripts/python scripts/prepare_site_photos.py path/to/folder

Each one is center-cropped to its slot's shape, resized and saved as WebP in
frontend/src/site/img/, where the site picks it up. See docs/site-images.md for
the prompts. Uses Pillow, which the backend already requires.
"""

import sys
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parents[1] / "frontend" / "src" / "site" / "img"

# slot name: (width, height) of the saved image
SLOTS = {
    "collection-amber-hollow": (1200, 750),
    "collection-coastal-garden": (1200, 750),
    "story-workshop": (1800, 771),
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


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    source = Path(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    found = 0
    for slot, (width, height) in SLOTS.items():
        matches = [
            source / f"{slot}{ext}" for ext in EXTENSIONS if (source / f"{slot}{ext}").is_file()
        ]
        if not matches:
            print(f"missing  {slot}  (the site keeps its drawing)")
            continue
        with Image.open(matches[0]) as image:
            if image.width < width or image.height < height:
                size = f"{image.width}×{image.height}"
                print(f"note     {slot} is {size}, smaller than {width}×{height}")
            picture = fit(image.convert("RGB"), width, height)
        target = OUT / f"{slot}.webp"
        picture.save(target, "WEBP", quality=80, method=6)
        print(f"saved    {target.name}  {target.stat().st_size // 1024} KB")
        found += 1
    print(f"{found} of {len(SLOTS)} slots filled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
