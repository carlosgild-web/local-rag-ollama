# 0008: Scope of the UI-improvements branch

**Status:** accepted (2026-11-08)

## Context

After Phase 4 and the 2026-11-06 end-to-end test, the user tried the app as a non-technical user would and asked for changes before starting Phase 5. These changes live on the `feature/ui-improvements` branch and merge to `main` only through a pull request. `CLAUDE.md` says not to add features outside the current phase, so this note records what came forward and why.

## Decision

**Built on the branch, at the user's request:**

- **Troubleshooter.** `GET /api/diagnostics` runs plain-language checks on Ollama, SQLite, the vector store and the job worker, each with a cause and a fix. The panel can be opened from any page. A status bar, a status pill, and paused controls make a broken system obvious.
  - `SIMULATE_FAULTS` (developer only) reproduces each failure.
  - A simulated L2 support ticket (ServiceNow style, numbered INC records) is saved under `DATA_DIR/support/`; it is never sent.
- **Upload flow.**
  - Review before processing: `POST /api/documents/check`.
  - The app then suggests a shelf and tags for every file (intake, [0009](0009-suggested-shelves-and-tags.md)).
  - Live progress, and readable job names in the Queue.
- **Collections in plain language:** tooltips, presets, a guide for unusual values, and a confirmation before Create, Rebuild and Reindex.

**Pulled forward from later phases:**

| Item | Planned in | Why now |
|---|---|---|
| Restore from trash (`POST /api/documents/{id}/restore`, refused if the name was reused on that shelf) | Phase 5 | The user deleted a document by mistake while testing and had no way back. |
| Citation passage viewer (`GET /api/chunks/{id}`) | Phase 6 | The user wanted to check an answer against the exact passage it came from. |
| README showcase: screenshots, an architecture diagram, "how it works", and a slide deck in `docs/showcase/` | Phase 9 | The user wants to present the project to potential employers now. |

**Not pulled forward:**
- the versions UI (Phase 5)
- the control panel (Phase 6)
- the evaluation (Phase 7)
- the demo compose profile, license, and personal-data audit of the history (Phase 9)

The license and the audit are needed only if the repository is made public. That is the user's decision, taken after seeing the showcase.

## Consequences

- Phases 5 and 6 are smaller: restore and the passage viewer are already done. Their checklists in `PLAN.md` should be updated when those phases start.
- The README describes the app as of v0.5.0. Phase 9 still owns the demo profile, the evaluation table, and the final polish.
- The branch adds one job type (`analyze_intake`) and one staging area (`DATA_DIR/uploads/intake/`). Both are covered by unit tests and the e2e kit.
