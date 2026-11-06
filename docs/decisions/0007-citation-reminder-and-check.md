# 0007: Citation reminder in the prompt code, and a citation check

**Status:** accepted (2026-11-06)

## Context

In the 2026-11-06 end-to-end test (`docs/test-reports/2026-11-06-e2e.md`), `qwen2.5:3b` cited correctly in only 64% of its answers. The rest had no citation, cited the wrong document, or cited a number that had no source. That breaks invariant 6, "citations are mandatory". The citation rule existed, but only in the system prompt at the top, far from where the model starts writing.

## Decision

- **A one-line hint in the prompt.** `build_prompt` adds "(Cite the sources you use as [1] to [N].)" between the question and "Answer:". The hint lives in the prompt code, not in the RAG profile, so it applies to every profile version without silently changing stored profiles. The profile's `system_prompt` still holds the main rules and is still required to contain the not-found rule.
- **Why this wording.** It was measured on 6 questions from the e2e run that had citation problems, using `qwen2.5:3b` with the app's real retrieval:

  | Prompt | Right facts | Valid citations | Wrongly "not found" |
  |---|---|---|---|
  | No hint | 6/6 | 4/6 | 0 |
  | Long reminder (all rules repeated, with an example) | 0/6 | 2/6 | 4 |
  | One-line hint (chosen) | 6/6 | 6/6 | 0 |

  The long reminder made the small model merge the citation and not-found rules. It answered "not found in the documents [1]", or only "[2]".
- **A citation check.** `app/retrieval/citations.py` rates each assistant answer as `ok`, `missing`, `invalid` or `not_applicable`, the last one for "not found" answers. The chat `done` event and every assistant message in `GET /api/sessions/{id}` carry this `citation_status`. The UI shows a warning when it is `missing` or `invalid`. The answer is kept as it is: the user sees the sources and decides.

## Consequences

- The prompt is about 60 words longer.
- The status is computed when read, not stored. If a purge later removes a message's source links, an older answer can turn `invalid`, which is accurate.
- The check can't tell whether a valid number points at the right document. Only an evaluation can measure that (Phase 7, and the e2e reviewer).
