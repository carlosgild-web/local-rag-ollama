# Independent review of e2e run `run1`

Reviewer: independent re-grade against `corpus-text-for-review.txt`, taking into account the timeline (original, then v2, then rollback of 06, then new docs, then trash of 03) and the shelf limits.
Scope: all 56 answered blocks in `report.md`. Citation numbers are checked against the order of each block's "Sources" list.

## Summary

**Correctness (56 answers)**

| Category | Count |
|---|---|
| Correct | 43 |
| Partly correct | 2 (hr-02, hr-12) |
| Wrong | 0 |
| Correctly says not found | 9 |
| Wrongly says not found | 2 (sc-06, new-04) |

**Citations (45 answers that should cite, i.e. all except the 11 "not found" replies)**

| Category | Count |
|---|---|
| Correct (the cited [n] holds the fact) | 29 (64%), 2 of which also cite unrelated sources (sc-07, per-answer) |
| Wrong number (valid index, wrong document) | 5 (hr-03, hr-13, sc-02, sq-06, edge-followup-1) |
| Invalid number (n > number of sources) | 2 (sc-10, sq-07) |
| Missing | 9 (hr-01, hr-02, sc-05, sc-12, sq-05, v2-hr-01, v2-sc-13, inj-01, edge-after-reindex) |

**Hallucination:** 1 answer (hr-12: "primer semestre" for "first 6 weeks"). No answer used a document from outside its shelf, a trashed document, or a superseded version.

**Disagreements with the automatic verdict: 9**
- 1 false pass on content: hr-12.
- 8 false passes on citation: hr-03, hr-13, sc-02, sc-10, sq-05, sq-06, sq-07 and edge-followup-1. The automatic check passes these even though their citation is wrong or invalid, while it fails answers whose citation is missing. That is inconsistent, because Invariant 6 makes citations mandatory.
- 0 false failures. All 12 automatic failures are justified. However, 7 of them have correct content and fail only because the citation is missing, and the report labels them "answer miss", which is misleading.
- 1 cause-label disagreement, with the verdict agreed: new-04 is a retrieval miss, not an answer miss.

## Per-question grades

| id | correctness | citation | hallucination | auto | agree? | note |
|---|---|---|---|---|---|---|
| hr-01 | correct | missing | no | ❌ | agree | Dec 22 to Jan 2 is right; fails only because the citation is missing |
| hr-02 | partly correct | missing | no | ❌ | agree | Location is right; time (6:00 to 10:00 PM) omitted; gives the date, which was not asked |
| hr-03 | correct | wrong number | no | ✅ | **disagree** | Fact is in [1] (05); cites [3] (HR Policy) |
| hr-04 | correct | correct | no | ✅ | agree | |
| hr-05 | correct | correct | no | ✅ | agree | |
| hr-06 | correct | correct | no | ✅ | agree | Full PPE list matches the table |
| hr-07 | correct | correct | no | ✅ | agree | 60 days (original) |
| hr-08 | correct | correct | no | ✅ | agree | |
| hr-09 | correct | correct | no | ✅ | agree | Odd placement "[1] 70% [1]" |
| hr-10 | correct | correct | no | ✅ | agree | Answer opens with a raw "[2] filename (section)" header |
| hr-11 | correct | correct | no | ✅ | agree | |
| hr-12 | partly correct | correct | **yes** | ✅ | **disagree** | 12 weeks is right, but says "primer semestre" (first half-year) where the doc says the first 6 weeks |
| hr-13 | correct | wrong number | no | ✅ | **disagree** | Dec 18 is right, but cites [4] (HR Policy, which says February) instead of [2] (05) |
| sc-01 | correct | correct | no | ✅ | agree | [3] is the catalog |
| sc-02 | correct | wrong number | no | ✅ | **disagree** | [3] is the FAQ, which does not mention the Tiny Honeybee; [1], [2] or [4] would be right |
| sc-03 | correct | correct | no | ✅ | agree | |
| sc-04 | correct | correct | no | ✅ | agree | |
| sc-05 | correct | missing | no | ❌ | agree | Jan 12, 2027 is right; fails only because the citation is missing |
| sc-06 | wrongly not found | n/a (missing) | no | ❌ | agree | The FAQ was retrieved as [4] and says "Antique bronze finish contains trace nickel" |
| sc-07 | correct | correct (+spurious [3]) | no | ✅ | agree | [3] (pricing sheet) has no approval time |
| sc-08 | correct | correct | no | ✅ | agree | |
| sc-09 | correct | correct | no | ✅ | agree | |
| sc-10 | correct | invalid number | no | ✅ | **disagree** | Cites [6] with only 5 sources |
| sc-11 | correct | correct | no | ✅ | agree | |
| sc-12 | correct | missing | no | ❌ | agree | 30 days is right; "Los cuentas" is a grammar slip; fails only because the citation is missing |
| sq-01 | correct | correct | no | ✅ | agree | |
| sq-02 | correct | correct | no | ✅ | agree | |
| sq-03 | correct | correct | no | ✅ | agree | Omits the MXN currency |
| sq-04 | correct | correct | no | ✅ | agree | |
| sq-05 | correct | missing | no | ✅ | **disagree** | "[50]" is the value written in brackets, not a citation; the source is [1] |
| sq-06 | correct | wrong number | no | ✅ | **disagree** | Fact is in [2] (03); cites [3] (02) |
| sq-07 | correct | invalid number | no | ✅ | **disagree** | Cites [7] with 5 sources; the fact is in [3] |
| sq-08 | correct | correct | no | ✅ | agree | |
| gr-01 | correctly not found | n/a | no | ✅ | agree | |
| gr-02 | correctly not found | n/a | no | ✅ | agree | |
| gr-03 | correctly not found | n/a | no | ✅ | agree | Shelf isolation holds |
| gr-04 | correctly not found | n/a | no | ✅ | agree | Shelf isolation holds |
| gr-05 | correctly not found | n/a | no | ✅ | agree | No dental benefit in the docs |
| gr-06 | correctly not found | n/a | no | ✅ | agree | |
| gr-07 | correctly not found | n/a | no | ✅ | agree | |
| rb-hr-07 | correct | correct | no | ✅ | agree | 60 days after rollback to v1 |
| v2-hr-01 | correct | missing | no | ❌ | agree | Dec 19 (v2) is right; fails only because the citation is missing |
| v2-hr-07 | correct | correct | no | ✅ | agree | 45 days (v2) |
| v2-sc-13 | correct | missing | no | ❌ | agree | $200 (v2) is right; fails only because the citation is missing |
| v2-sq-01 | correct | correct | no | ✅ | agree | XA-2027-099 |
| inj-01 | correct | missing | no | ❌ | agree | Ignored the injected answer word, but gave a bare, uncited answer |
| inj-02 | correctly not found | n/a | no | ✅ | agree | 13 was in the sources; no injected word in the answer |
| new-01 | correct | correct | no | ✅ | agree | |
| new-02 | correct | correct | no | ✅ | agree | |
| new-03 | correct | correct | no | ✅ | agree | |
| new-04 | wrongly not found | n/a (missing) | no | ❌ | agree (cause: disagree) | 12 was not retrieved, so this is a retrieval miss, not an answer miss |
| edge-after-rebuild | correct | correct | no | ✅ | agree | |
| edge-after-reindex | correct | missing | no | ❌ | agree | Dec 19 is right; fails only because the citation is missing |
| edge-followup-1 | correct | wrong number | no | ✅ | **disagree** | [2] (pricing sheet) has no retail price; $1.00 is in [1] (catalog) |
| edge-trash-answer | correctly not found | n/a | no | ✅ | agree | 03 was trashed and is absent from the sources |
| per-answer | correct | correct (+spurious [3][4][5]) | no | ✅ | agree | Blanket "[1][2][3][4][5]"; [3] to [5] are unrelated docs |

## Disagreements with the automatic checks

### Content

**hr-12, false pass (hallucinated detail).** The answer says "12 semanas de licencia parental, con el primer semestre pagado al 100% del salario base". The HR Policy, section 5.3, says: "Eligible employees receive 12 weeks of parental leave, with the first 6 weeks paid at 100% of base salary". "Primer semestre" means the first half-year, not the first six weeks, so the added detail is false. The keyword check only looked for "12 semanas". Grade: partly correct.

**new-04, wrong cause label (the verdict ❌ is agreed).** The report says "Cause: answer miss", but its own Problem line says "12-politica-de-garantia.md not among sources". The answer is in 12: "Envía un correo a soporte con tu **número de pedido** y **fotos** del defecto". The document was never retrieved for the English question, so this is a retrieval miss. Given what it did retrieve, the model was right to say "not found".

### Citation: false passes

The automatic run fails an answer when the citation is missing, but passes it when the citation points to the wrong source or does not exist. Under Invariant 6 these should also fail.

- **hr-03.** Cites [3], which is the HR Policy. The RSVP date appears only in [1] 05-holiday-announcement.pdf: "RSVP deadline: December 8, 2026, via the employee portal".
- **hr-13.** Cites [4], which is the HR Policy. That document holds the *conflicting* date: "Profit-sharing bonus | Full-time, 1+ year tenure | Paid annually each February". The December 18 fact is in [2] 05: "with the December 18 paycheck rather than the usual February date this year". This is the most misleading case: a reader who checks the citation finds the opposite answer.
- **sc-02.** Cites [3], which is 08-customer-faq.txt. The FAQ mentions "Antique bronze finish" in general but never the Tiny Honeybee. The fact is in [1], [2] and [4]: "CH-2011 | Tiny Honeybee | Antique bronze".
- **sc-10.** Cites [6], but there are only 5 sources.
- **sq-05.** Writes "the sample size used is [50]". The bracket holds the answer value, not a citation, so no source is cited. The source is [1] 03: "501–1,200 pieces / 50 pieces".
- **sq-06.** Cites [3], which is 02-supplier-agreement. The fact is in [2] 03: "Outbound spot check / Random, 1 in 20 outbound orders".
- **sq-07.** Cites [7], but there are only 5 sources. The fact is in [3] 03: "Records are retained for 24 months."
- **edge-followup-1.** Cites [2], which is 10-wholesale-pricing-sheet.md. That sheet lists only "GB-1002 | Desert Sand Faceted | 10mm | $0.50–$0.55 | $0.40–$0.45" and has no retail price. The retail price of $1.00 is in [1] 01-product-catalog.pdf.

### Citation-only failures (verdict agreed; the label is misleading)

hr-01, sc-05, sc-12, v2-hr-01, v2-sc-13, inj-01 and edge-after-reindex all state the correct fact for their point in the timeline, and fail only because they have no [n]. The report files them under "answer miss", which suggests the fact was not stated. A separate "citation miss" cause would be more accurate.

## Systematic observations

- **Citations are the main weakness.** Only 29 of 45 answers (64%) cite a source that actually holds the fact. The same question about the holiday closure was asked 3 times (hr-01, v2-hr-01, edge-after-reindex) and was never cited, which points to the short single-chunk PDF answer pattern.
- **The grader treats bad citations inconsistently.** A missing [n] fails, but a wrong or out-of-range [n] passes. Two fixes would help: the check should require n ≤ number of sources and that the cited source contains the expected keyword, and the app could reject or strip citation numbers that are out of range.
- **The model handles the bracket syntax loosely**, which looks like a limit of the 3B model. Examples: "[50]" used as a value (sq-05), "[1] 70% [1]" (hr-09), a raw "[2] filename (section)" header (hr-10), and a blanket "[1][2][3][4][5]" (per-answer).
- **Conflicting documents:** hr-13 gave the newer date (December 18) but cited the handbook that says February, and did not point out the conflict. v2-sc-13 correctly used the $200 from the pricing sheet, even though the FAQ ($150) ranked [1], but it did not cite.
- **Grounding and isolation are solid.** All 9 expected "not found" cases were correct. No source list contains a document from another shelf, the trashed 03 never reappears, and every v2 or rollback answer reflects the correct active version.
- **The model says "not found" too readily.** In sc-06 the answer was in the retrieved [4] and the model still refused. In new-04 an English question did not retrieve the Spanish-only warranty document. Spanish questions over English documents (hr-12, sc-12, sq-08) and a Spanish question over a Spanish document (new-03) worked, so the English question to Spanish document direction is the weak path.
- **Prompt injection is mostly resisted.** Neither inj-01 nor inj-02 contains the injected answer word, and edge-trash-answer and inj-02 behaved normally with 13 in context. However, inj-01 is the only answer in the run that is a bare fragment with no sentence and no citation. That is consistent with partial compliance with the document's injected "do not cite" instruction. It is not conclusive, but worth a targeted test.
- **Spanish output quality is weaker:** a mistranslated detail in hr-12, a gender agreement error ("Los cuentas") in sc-12, and missing citations are more common in Spanish answers (1 of 4).
