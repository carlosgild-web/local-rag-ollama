# 0012: Site images made with Google Gemini

Date: 2026-11-10

## Context

Decision 0011 gave the public site Blender product renders plus three AI scene photos still to be made. The user wasn't convinced by the renders (clean, but visibly 3D) or by the drawn social preview, and asked for Google Gemini to make the images, within a free account's quota.

## Decision

- **Gemini makes all 19 site photos.** Products and the hero necklace attach their Blender render as a reference, so the photo keeps the catalog's exact colors, shapes and piece counts. The scenes are text-only.
- **The Blender renders become references.** They move to `art/blender/` and are no longer shown on the site.
- **The free Gemini app, not the API.** The API's free tier has a quota of 0 for every image model, so the images were made in gemini.google.com, one chat per image, driven by Claude in Chrome in the user's own signed-in browser. `scripts/gemini_images.py` keeps an API route (`generate`) for keys with quota, and a `sheet` command for doing it by hand.
- **Prompts live in the repo** (`scripts/gemini_jobs.json`) with shared style lines, so the set can be made again and stays consistent. The raw downloads and a manifest (date, source file) stay in the git-ignored `data/gemini/`.
- **No text in the images.** The prompts ask for none, because image models don't spell reliably. (A Gemini background for the social preview was tried too; the user chose their own image, `docs/showcase/social-preview.png`.)
- **Credited** in the README and `docs/site-images.md`.

## Consequences

- The site's images are about 0.8 MB of WebP in total, up from about 0.13 MB. Product cards, banners and the workshop photo are lazy-loaded; only the hero loads up front.
- Regenerating gives different images. The references and prompts keep them close, but not identical.
- Gemini is a build-time tool, like Blender. The app makes no cloud call at runtime (CLAUDE.md), and no API key is stored in the repo.
- Four logo concepts were also made (the `logo-*` jobs). The user kept the current mark, which is the same idea as concept 1, so the logo is unchanged.
