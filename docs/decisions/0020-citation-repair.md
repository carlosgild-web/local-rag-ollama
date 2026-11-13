# 0020: Repairing citation numbers after the answer

**Status:** accepted (2026-11-13)

## Context

The first evaluation baseline (decision 0019; `qwen2.5:3b`, hybrid, 5 passages, temperature 0) passed 37 of 53 questions. Retrieval found the right file for all of them. The largest group of failures, 7 of 16, were answers with the right fact and the wrong citation number:
- $1.60 retail cited to the wholesale pricing sheet, which has no retail prices
- the December 18 bonus date cited to the handbook, which says February
- `[7]` when only 5 sources were sent
- section titles ("[4. Separation of Employment]") used as citations

`citation_status` only checks that a number is in range (decision 0007), so most of these looked "ok". Prompt changes are risky with this model: a longer citation reminder took facts from 6/6 to 0/6 (decision 0007).

## Decision

After the answer is written, a deterministic step (`app/retrieval/citation_repair.py`) checks each citation against the passages sent to the model. **It changes only the `[n]` markers, never the words.**

- **Claim:** the text between a run of markers and the previous run. So in "The price is $1.60. This is in [1].", the figure belongs to `[1]`.
- **Score:** each passage is scored on the claim's numbers (3 points each, since another document rarely has the same figures) and content words.
- **When a marker changes**, only on clear evidence:
  - an out-of-range number or a section title → the best passage
  - the cited passages lack a number the claim states and another passage has all of them → that passage
  - no number decides, but another passage shares at least 2 more words and twice as many → that passage
  - in a run of several markers, one scoring under half of the best cited one → dropped
  - a sentence after the last marker with no citation → the passage that clearly supports it (a shared number or 3 words, no tie)
- Anything less clear stays as the model wrote it. "Not found" answers aren't touched.

**Where it runs:**
- The chat saves the repaired answer. The text streams as the model writes it, then the UI swaps in the saved message, as it already did, so console and portal both show the repaired citations. The `done` event's `citation_status` is computed on the repaired text.
- Evaluation runs repair by default, like the chat. `repair_citations: false` on `POST /api/eval/runs` (or `--no-repair` in the CLI, or the checkbox on the page) measures the model's own citations.

**Golden set:** checking the failures showed one case was too strict. The wholesale pricing sheet also lists the Tiny Honeybee's finish, so it is now an expected source for that question.

## Measurements

The baseline answers replayed through the repair. The answers are identical at temperature 0, and the repair only touches markers.

| | Passed | Citations to the right file | Facts | Wording groups all passed |
|---|---|---|---|---|
| Baseline | 70% (37/53) | 79% | 84% | 25% |
| With repair | 81% (43/53) | 93% | 84% | 50% |

Six questions were fixed and none broke:
- the profit-sharing bonus date
- the resignation notice (section titles became `[3]` and `[4]`)
- the Opal Mist retail price
- the QC sample size (a wrong extra marker was dropped)
- the outbound spot checks
- the Quality Register retention (`[7]` became `[1]`)

## Consequences

- What's saved isn't exactly what streamed: a citation number can change when the answer finishes. Every change moves a citation to a passage that contains the claim's figures or words.
- Two Spanish questions over English documents share only a number with the passages, so no passage wins and they stay as written.
- A claim with no figures, worded differently from its passage, can't be checked. Those citations stay as the model wrote them.
- `message_sources` doesn't change: the passages sent and their ranks are the same, only the numbers in the text move. Reproducibility (invariant 5) holds.
