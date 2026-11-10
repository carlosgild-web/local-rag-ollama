/**
 * The site's photos (decision 0011), bundled by Vite from src/site/img/.
 * All of them are made with Google Gemini (products and the hero from Blender
 * reference renders in art/blender/) and prepared by scripts/prepare_site_photos.py;
 * see docs/site-images.md.
 * A missing file is fine: the page falls back to its SVG drawing.
 */
const FILES = import.meta.glob("./img/*.webp", { eager: true, query: "?url", import: "default" }) as Record<string, string>;

export function photo(name: string): string | undefined {
  return FILES[`./img/${name}.webp`];
}
