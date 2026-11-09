# 0010: An employee portal with Luna, an assistant over every shared shelf

**Status:** accepted (2026-11-08)

## Context

The app only showed the admin side: uploading files, versions, the queue, chat for the person who manages the documents. The user asked for the other side too: a simulated **internal company website** for the fictional *Hilda & Luna Beadworks*, where employees ask an assistant questions answered only from the documents the RAG system indexed. It has a full-page chat and a floating chat bubble, ES/EN switchable, and a dashboard button that opens it. This is not in `PLAN.md`; it starts after the UI-improvements branch (0008).

## Decision

**Same app, separate route tree.** The portal lives at `/intranet/*` in the same React build, outside the admin layout, and is lazy-loaded. FastAPI already serves the SPA (`api/static.py`), so there's no second server, no CORS and still one Docker image.

**Luna searches every shelf the admin shares.**
- `collections.portal_visible` defaults to true, and the Collections page has a switch for it. `PATCH /api/collections/{id}` goes through `service.set_portal_visible`, which writes the audit entry `collection_portal_visibility` (invariant 7).
- A blue/green swap copies the flag at swap time, so a toggle made during a rebuild is kept.
- `retrieve_many` compares scores only where they mean the same thing:
  - shelves that share an embedding model give **one** vector list, ordered by cosine similarity;
  - FTS5 runs **once** over all the shelves;
  - RRF fuses those lists by rank, so vectors from different models are never compared (invariant 4).
- **Not per shelf.** The first version fused each shelf's own lists. In the real run, the one-document `meetings` shelf was ranked first for every question, because its best chunk was always #1 in its own list. With the lists merged, the kiln-safety question got 4 of its top 5 chunks from the safety manual instead of 1.
- With one shelf the result is exactly the old `retrieve`, which now just calls `retrieve_many`.

**A channel on each chat.**
- `chat_sessions.channel` is `admin` or `intranet` (migration `0005_portal`). `POST /api/chat` with `channel: "intranet"` ignores `collection_id` and searches the portal shelves. Its session has no `collection_id`, and follow-ups stay in the channel they started in.
- `GET /api/sessions` lists only the admin channel unless asked otherwise, so the console's history isn't filled with employee chats, while the dashboard can still show them.
- Sources, the profile version and feedback are stored exactly as for admin chats (invariant 5).

**Answer language.**
- `answer_language: "en" | "es"` adds one rule, "4. Write the answer in Spanish.", after the profile's rules. It is one short line, because 0007 found longer rule lists confuse `qwen2.5:3b`.
- The not-found rule is unchanged. The portal recognizes the not-found reply in either language and shows a friendly bilingual message instead.

**Simulated internal access, no login.** The portal says so in its footer. Anyone who can reach the server can open both the portal and the console, as before. Real authentication would sit in front of `/intranet` and the admin API; the per-shelf flag is the piece it would build on.

**Demo corpus in the repo.**
- The 11 fictional sample documents live in `backend/demo/hilda-luna/<shelf>/`. They're under `backend/` so the Docker image, which copies only `backend/`, includes them.
- `python -m app.cli seed-demo` ingests them through the normal service, one shelf per folder, tagged `demo,<shelf>`. Re-running it skips every file as a duplicate.
- Each document is marked as fictional, and `backend/demo/README.md` says so too.

**Fonts are bundled, not fetched.** At runtime the app must make no cloud calls, so Google Fonts is out. Two `@fontsource-variable` packages (Fraunces for display, Figtree for body text) are bundled by Vite and load only with the portal's lazy chunk; they are the only new dependency. The plan said Inter for body text; Figtree was used instead because it is friendlier, and the console already has Inter's neutral look.

**Logo.** An original bead-moon mark: graduated glass beads on one thread form a crescent, with an amber star charm. It is drawn from geometry in `src/portal/Logo.tsx`, and `public/hl-mark.svg` and `public/hl-logo.svg` are generated from the same numbers. Two alternative concepts were shown to the user.

**Static content.** The home page text (dates, handbook figures, news) is written once in `src/portal/content.ts` from the demo documents. It doesn't update when the documents change; Luna's answers always come from the indexed documents.

## Consequences

- An employee question with no visible shelf, or with empty shelves, answers "not found" without calling the model.
- Searching N shelves costs N vector queries and N FTS queries, but only one embedding call per distinct model.
- The admin chat still searches one shelf per conversation; nothing in it changed.
