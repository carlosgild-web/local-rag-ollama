# Images for the demo company's website

The public site at `/site` (decision 0011) uses two kinds of images. Both live in `frontend/src/site/img/` as WebP. Any image that's missing falls back to the site's SVG drawing, so the site always works.

| Kind | Images | How they're made |
|---|---|---|
| **Product renders** | 5 beads, 5 charms, 4 findings, the starter set, the hero necklace | Rendered by Blender from `scripts/render_site_art.py`: geometry and shaders, no photos. Original, no license questions, and they match the catalog exactly. |
| **Scene photos** | Amber Hollow banner, Coastal Garden banner, workshop photo | Generated once with an AI image tool, then prepared by `scripts/prepare_site_photos.py`. |

Blender is only a build-time tool; the app never needs it, and no image is fetched at runtime.

## Product renders (Blender)

From the repo root, with Blender 4.x or 5.x installed:

```bash
blender -b --factory-startup -P scripts/render_site_art.py -- --out frontend/src/site/img
blender -b --factory-startup -P scripts/render_site_art.py -- --only GB-1014 hero-strand --samples 32   # a few, quick
```

On a laptop CPU the full set takes about 10–15 minutes at the default 96 samples. The product list at the top of the script mirrors `frontend/src/site/content.ts`; change both together.

## Scene photos (AI-generated)

1. Generate each image below with the AI tool of your choice. Adobe Firefly's terms suit commercial use; ChatGPT and Midjourney work too, so check their terms. Use a landscape format and the largest size the tool offers.
2. Save them in one folder, named exactly after their slot, for example `collection-amber-hollow.png`.
3. Run:

   ```bash
   backend/.venv/Scripts/python scripts/prepare_site_photos.py path/to/folder
   ```

   It center-crops each image to its slot's shape, resizes it and writes `frontend/src/site/img/<slot>.webp`.
4. Look at the result on the site. Check for garbled "text", extra fingers or a logo, and regenerate if needed.

All three prompts share one style line so the set looks like one shoot:

> *Style: editorial product photography, natural light, shallow depth of field, warm and slightly muted color, fine film grain. No text, no letters, no logos, no watermark, no faces.*

### `collection-amber-hollow` (shown at 16:10; text sits over the top third)

> Three-quarter overhead view of handmade lampwork glass beads in warm amber, rust orange and deep forest green, scattered on a dark walnut table, with a few small antique-bronze pewter charms shaped like acorns, mushrooms and a crescent moon, and two dry oak leaves. Low late-afternoon window light from the left. Keep the top third darker and uncluttered. *+ style line*

### `collection-coastal-garden` (shown at 16:10; text sits over the top third)

> Three-quarter overhead view of handmade lampwork glass beads in blush pink, seafoam mint, pale butter yellow and periwinkle, scattered on pale natural linen, with a few small polished silver charms shaped like scallop shells and leaves, and a sprig of sea lavender. Bright, airy morning light. Keep the top third soft and uncluttered. *+ style line*

### `story-workshop` (shown at 21:9, the full width of the "Our story" card)

> Close-up of an artisan's hands at a lampworking torch, winding a glowing molten orange glass bead onto a steel mandrel. Jars of colored glass rods on a small workbench, a dark background, warm light from the flame. Documentary style; hands and forearms only. *+ style line*

The alt text for each photo is in `content.ts` (`photoAlt`). If an image ends up showing something different, update its alt text to match.

## Credits

When the scene photos are added, say in the README that they are AI-generated and name the tool.
