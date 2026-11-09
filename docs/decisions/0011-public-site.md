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

**Drawn art, no photos.** Beads (round, faceted, swirl, lentil), charms, findings and the collection strands are SVG drawn from geometry in `src/site/art.tsx`, reusing the logo's `Bead`. They are original, need no license and ship in the bundle. Runtime cloud calls are not allowed, so nothing is hotlinked.

**Demo forms.** The newsletter, wholesale application and contact forms check required fields, then clear and say "Demo site: nothing was sent and nothing was stored". No request is made.

**Same brand, warmer look.** The site uses cream, sand, rust and forest tokens (`--color-hl-*` in `index.css`), taken from the Amber Hollow collection. It keeps the bead-moon logo, the bundled Fraunces and Figtree fonts, and the ES/EN switch. The language is stored under the same key, so it carries into the intranet. `LangSwitch` and the tab-title hook moved to `portal/brand.tsx` for both layouts. Text colors meet WCAG AA; `hl-amber-light` exists only so amber text on forest green passes.

**No public chat yet.** Luna stays employee-only. A customer assistant would need a `public` channel and a per-shelf public flag; it is left for later.

## Consequences

- No new dependencies and no backend changes. The site is its own set of lazy chunks (about 25 kB gzipped with its content), loaded only on `/site`.
- Prices and policies on the site are copies. If a demo document changes, `content.ts` must be updated by hand.
