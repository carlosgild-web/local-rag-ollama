# Images for the demo company's website

The public site at `/site` (decision 0011) shows 19 photos: the hero necklace, two collection banners, the workshop photo and 15 product shots. All of them were made with **Google Gemini** ([decision 0012](decisions/0012-site-images-with-gemini.md)) and live in `frontend/src/site/img/` as WebP. A missing image falls back to the site's SVG drawing, so the site always works. Nothing is fetched at runtime, and the app never calls Gemini.

| Kind | Images | How they're made |
|---|---|---|
| **Products and hero** | 5 beads, 5 charms, 4 findings, the starter set, the hero necklace | A Blender render (`art/blender/`) is attached as the reference, and Gemini turns it into a photo while keeping the object's colors, shape and arrangement. |
| **Scenes** | Amber Hollow banner, Coastal Garden banner, workshop photo | Text prompt only. |
| **Social preview** | `docs/showcase/social-preview.jpg` | Gemini makes the background; `scripts/make_social_preview.py` adds the title text, because image models don't spell reliably. |

## The prompts

Every prompt is in [`scripts/gemini_jobs.json`](../scripts/gemini_jobs.json): one job per image, with its shape, its reference render (if any) and its text. Shared style lines keep the set consistent:

- `style`: the photo look (soft studio light, shallow depth of field, warm muted color, no text or logos)
- `product_style`: "turn this 3D render into a photorealistic macro product photo of the same object…", used by every product
- `logo_style`: for the logo concepts, which are drawings, not photos

To see the final prompt for each job: `backend/.venv/Scripts/python scripts/gemini_images.py prompts`.

## Making the images

### In the Gemini app (how this set was made)

The Gemini API's free tier allows no image generation, so this set was made in the free Gemini app at gemini.google.com, one new chat per image. The steps were automated with Claude in Chrome, but they're the same by hand:

1. Run `backend/.venv/Scripts/python scripts/gemini_images.py sheet`. It writes `data/gemini/prompts.html`, a page with every prompt, a copy button and the reference image to attach.
2. For each job, open a new chat, attach the reference (if there is one) and paste the prompt.
3. Download the full-size image and save it as `data/gemini/raw/<name>.jpg` (or `.png`). The `data/` folder is git-ignored.

About 40 seconds per image; the free app had no trouble with 24 images in a day.

### With the API (if your key has image quota)

```bash
backend/.venv/Scripts/python scripts/gemini_images.py check      # lists image models, makes one test image
backend/.venv/Scripts/python scripts/gemini_images.py generate   # makes every missing image
```

The key comes from the `GEMINI_API_KEY` environment variable and is sent only in a request header. When the quota runs out, the run stops; run it again later and it skips finished images.

### Preparing them for the site

```bash
backend/.venv/Scripts/python scripts/prepare_site_photos.py      # → frontend/src/site/img/*.webp
backend/.venv/Scripts/python scripts/make_social_preview.py      # → docs/showcase/social-preview.jpg
```

`prepare_site_photos.py` center-crops each image to its slot's shape, resizes it and saves WebP. Use `--only NAME …` to redo just a few.

Then look at the result on the site. Check for garbled "text", a wrong number of beads, or a logo, and regenerate if needed. The alt text for each photo is in `content.ts`; if an image shows something different, update its alt text to match.

## The Blender reference renders

`art/blender/*.webp` are 3D renders from [`scripts/render_site_art.py`](../scripts/render_site_art.py), made from geometry and shaders only. They pin down each product's exact colors and shape, so the Gemini photo matches the catalog. To render them again (Blender 4.x or 5.x, about 10–15 minutes on a laptop CPU):

```bash
blender -b --factory-startup -P scripts/render_site_art.py
blender -b --factory-startup -P scripts/render_site_art.py -- --only GB-1014 --samples 32   # a few, quick
```

The product list at the top of the script mirrors `frontend/src/site/content.ts`; change both together.

## Credits

The site's photos and the social preview background were made with Google Gemini. Hilda & Luna Beadworks and its products are fictional.
