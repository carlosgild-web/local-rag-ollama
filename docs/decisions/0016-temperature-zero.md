# 0016: Temperature 0 for answers

**Status:** accepted (2026-11-13)

## Context

PLAN.md section 6 started answers at temperature 0.2. On 2026-11-12 the portal was asked "Can I get a custom bead color made?" twice, with the same retrieved chunks both times. The first answer left out the contact email that had just been edited in the FAQ. The second included it.

The exact prompt was then replayed against Ollama (`qwen2.5:3b`) 5 times per setting:

| Context | Temperature 0.2 | Temperature 0 |
|---|---|---|
| FAQ chunk retrieved | 2 different answers in 5 runs | 1 answer in 5 runs, complete |
| Wrong shelf (no FAQ chunk) | 5 different answers in 5 runs | 1 answer in 5 runs, still wrong |

## Decision

- The default `LLM_TEMPERATURE` is `0` (`core/config.py`, `.env.example`). It seeds the `default` RAG profile on a new install, and the CLI uses it.
- Existing installs change it with a new `default` profile version (`POST /api/profiles` with `{"temperature": 0}`). That change is versioned and audited, and switching back to the previous version undoes it.

## Consequences

- The same question over the same sources gives the same answer. That fits invariant 5 (reproducible answers) and makes Phase 7 comparisons meaningful: a change in score comes from the change being tested, not from sampling.
- It makes answers **repeatable, not more correct**. A wrong answer becomes reliably wrong (the wrong-shelf row above), so grounding stays a Phase 7 item.
- Asking again no longer gives a different wording. Small models at temperature 0 can repeat themselves on long answers; ours are short, but watch for it.
- Shelf suggestions at upload keep their own fixed temperature (0.1).
