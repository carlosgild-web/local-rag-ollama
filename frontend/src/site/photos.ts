/**
 * The site's photos (decision 0011), bundled by Vite from src/site/img/.
 *   - Product shots, the starter set and the hero necklace are rendered by
 *     scripts/render_site_art.py (Blender).
 *   - Scene photos (collection banners, workshop) are AI-generated, prepared by
 *     scripts/prepare_site_photos.py; see docs/site-images.md.
 * A missing file is fine: the page falls back to its SVG drawing.
 */
const FILES = import.meta.glob("./img/*.webp", { eager: true, query: "?url", import: "default" }) as Record<string, string>;

export function photo(name: string): string | undefined {
  return FILES[`./img/${name}.webp`];
}

/** Scene photos that are generated with an AI tool, not rendered. */
export const AI_PHOTOS = ["collection-amber-hollow", "collection-coastal-garden", "story-workshop"] as const;
