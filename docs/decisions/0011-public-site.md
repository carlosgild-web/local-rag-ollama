# 0011: A public website for the demo company, with a simulated staff sign-in

**Status:** accepted (2026-11-09)

## Context

The employee portal (0010) showed the inside of *Hilda & Luna Beadworks*. To make the demo feel like a real company, the user asked for its outside face as well: a public website modeled on real bead and charm makers, with a way from it into the intranet. This is not in `PLAN.md`; it continues the portal work on `feature/employee-portal`.

Real makers' sites (Nunn Design, Green Girl Studios) share a pattern:
- a top bar with wholesale and sign-in links
- seasonal collection banners and "shop by" category tiles
- wholesale as a main path
- a maker story and a newsletter
- a footer grouped into customer care, company and resources

The site follows that pattern.

## Decision

**Route `/site`, console stays at `/`.** The site is a third lazy route tree in the same React build (`src/site/`), next to `/intranet`. Anyone who clones the repo still lands on the RAG console. The backend already serves the SPA for any path, so nothing changed there.

**Pages:**
- Home, with collections, favorites, story, wholesale and a newsletter
- Catalog
- Wholesale
- Help, covering shipping, returns, FAQ and contact
- `/site/staff`, the staff sign-in

**Content rule: customer-facing documents only.** The text in `src/site/content.ts` is written from:
- the product catalog
- the shipping and returns policy
- the customer FAQ
- the wholesale pricing sheet
- the company overview in the handbook

Internal facts stay on the intranet: sales figures, the foundry delay, HR policy, holiday dates. Wholesale per-SKU prices show only as "trade price with an account", which is how real makers do it. Like `portal/content.ts`, the text is static and doesn't follow document changes.

**Simulated sign-in, said plainly.** *Employee login* opens a card labeled "Simulated sign-in" with one button, *Enter as demo employee*, that goes to `/intranet`.
- There is no username or password field, so the page can't suggest security that isn't there.
- `/intranet` is still reachable directly, as 0010 says. Real authentication would sit in front of `/intranet` and the admin API.

**Images: Blender renders plus a few AI scenes (hybrid).** First the site used only SVG drawings; the user then asked for realistic images. The laptop has integrated graphics and 7 GB of RAM, too little to run an image model locally next to Ollama, so:
- **Product renders.** Every bead, charm and finding, the starter set and the hero necklace are rendered by Blender from `scripts/render_site_art.py`, with geometry and shaders only:
  - lampwork glass with dots, swirls, facets and a bored hole
  - pewter charms cut from the same outlines as the SVG drawings, in gold, rhodium or antique bronze
  - warm paper underneath and a macro-lens depth of field

  The images are original, match the catalog exactly, and can be rendered again in about 10 minutes. Blender is a build-time tool only.
- **Scene photos.** The two collection banners and the workshop photo are generated once with an AI image tool, using the prompts in `docs/site-images.md`, and prepared by `scripts/prepare_site_photos.py` (Pillow, already a backend requirement). The README credits them as AI-generated.
- Images are WebP in `src/site/img/`, picked up with `import.meta.glob`. Any missing image falls back to the SVG drawing (`src/site/art.tsx`), so the site works before the AI photos exist. Nothing is fetched at runtime.

**Demo forms.** The newsletter, wholesale application and contact forms check required fields, then clear and say "Demo site: nothing was sent and nothing was stored". No request is made.

**Same brand, warmer look.** The site uses cream, sand, rust and forest tokens (`--color-hl-*` in `index.css`), taken from the Amber Hollow collection. It keeps the bead-moon logo, the bundled Fraunces and Figtree fonts, and the ES/EN switch. The language is stored under the same key, so it carries into the intranet. `LangSwitch` and the tab-title hook moved to `portal/brand.tsx` for both layouts. Text colors meet WCAG AA; `hl-amber-light` exists only so amber text on forest green passes.

**A reviewer's guide, outside the fiction.** Someone reviewing the portfolio, such as a recruiter, starts at the website and needs to learn three things: that it's a demo, which path to follow, and that the real product is the RAG console behind the intranet. The guide in `src/portal/DemoGuide.tsx` tells them.
- **Public site:** a one-line strip pointing to *Employee login → intranet → RAG console*.
- **Intranet:** a banner with *How this demo works* and *Open the RAG admin console* (a new tab, so the intranet stays open).
- **The panel:** a right-side drawer (the shared `Dialog` with `side="right"`) explaining what the project is, the four-step path with "you are here", and things to try.
- **Look:** deliberately not the company's. Neutral charcoal, a dashed edge, a monospace "Portfolio demo · not part of the company design" tag and the console's plain font, so nobody mistakes it for Hilda & Luna's branding.
- **Hiding:** closing it collapses it to a *Demo guide* pill at the bottom left, away from Luna's bubble. The choice is remembered in the browser (`hl-demo-guide`) for both sites, so clean screenshots are easy and the path is never lost.

**No public chat yet.** Luna stays employee-only. A customer assistant would need a `public` channel and a per-shelf public flag; it is left for later.

## Consequences

- No new app dependencies and no backend changes; Blender is only needed to re-render the images. The site is its own set of lazy chunks (about 25 kB gzipped with its content), loaded only on `/site`.
- Prices and policies on the site are copies. If a demo document changes, `content.ts` must be updated by hand.
