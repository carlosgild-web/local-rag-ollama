"""Builds the GitHub social preview (1280×640) from the Gemini background.

The background is data/gemini/raw/social-background.png (see scripts/gemini_images.py),
with the objects on the right and open space on the left. The title text is drawn
here, because image models don't spell reliably. Run from the repo root:

    backend/.venv/Scripts/python scripts/make_social_preview.py

Writes docs/showcase/social-preview.jpg. Upload it in the repo's Settings →
General → Social preview.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "gemini" / "raw"
OUT = ROOT / "docs" / "showcase" / "social-preview.jpg"
W, H = 1280, 640
FONTS = Path("C:/Windows/Fonts")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for candidate in (FONTS / name, Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default(size)


def background() -> Image.Image:
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        path = SOURCE / f"social-background{ext}"
        if path.exists():
            image = Image.open(path).convert("RGB")
            scale = max(W / image.width, H / image.height)
            image = image.resize(
                (round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS
            )
            left, top = (image.width - W) // 2, (image.height - H) // 2
            return image.crop((left, top, left + W, top + H))
    raise SystemExit(
        f"Missing {SOURCE / 'social-background.png'}: make it with scripts/gemini_images.py first."
    )


def main() -> int:
    image = background()
    # A soft cream panel on the left keeps the title readable on any background.
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rectangle((0, 0, 600, H), fill=(251, 246, 238, 215))
    panel = panel.filter(ImageFilter.GaussianBlur(40))
    image = Image.alpha_composite(image.convert("RGBA"), panel).convert("RGB")

    draw = ImageDraw.Draw(image)
    bark, muted, rust = (46, 34, 25), (90, 72, 58), (168, 72, 31)
    x = 64
    draw.text((x, 150), "LOCAL RAG · OLLAMA", font=font("segoeuib.ttf", 20), fill=rust)
    draw.multiline_text(
        (x, 188),
        "Ask your own\ndocuments,\nfully offline.",
        font=font("georgiab.ttf", 64),
        fill=bark,
        spacing=10,
    )
    draw.multiline_text(
        (x, 430),
        "Grounded answers with citations,\nversioned documents, hybrid search.",
        font=font("segoeui.ttf", 28),
        fill=muted,
        spacing=8,
    )
    draw.text(
        (x, 540),
        "FastAPI · SQLite FTS5 · Chroma · React · Docker",
        font=font("segoeuib.ttf", 18),
        fill=muted,
    )
    image.save(OUT, "JPEG", quality=88, optimize=True)
    print(f"Wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
