# 0021: A glossary that writes the documents' words into the question

**Status:** accepted (2026-11-14)

## Context

After the citation repair (decision 0020), the live run passed 45 of 53 golden-set questions. Three of the failures were "not found" although the right passage was among the top 5:
- "How many vacation days do I have?": the HR policy says PTO, and the model doesn't connect the two words. Asking for "PTO days" works.
- Two Spanish questions over English documents: "¿Cuántos días tengo para devolver cuentas sin usar?" and "¿Cuál es el recargo para pedidos urgentes del proveedor?". The documents say *return*, *beads*, *surcharge* and *rush*.

Retrieval already found the right file for every question, so the problem was the model reading the question against the passage, not the search.

## Decision

**A company-wide glossary**: each entry is a word people use and the words the documents use, e.g. *vacation* → *PTO, paid time off*.
- It's stored in a `glossary_terms` table (migration 0009) and edited in a **Glossary** card on the Collections page. A "try a question" box there shows the question as it will be asked.
- Every add and delete is audited.
- There's one list for all shelves: "vacation = PTO" holds everywhere, the portal searches several shelves at once, and a per-shelf list would have to survive blue/green rebuilds.

**Expansion**: the meaning is written into the question right after the word, so both the search and the model see it:

> How many vacation (PTO, paid time off) days do I have?

- Matching ignores case and accents, takes whole words only, and accepts plural endings.
- Longer terms win over shorter ones.
- Each term is used once, and is skipped when its meaning is already in the question.
- It applies wherever a question is asked: `prepare_context` and `prepare_context_many` (console chat, portal, CLI `ask`), `POST /retrieve` and evaluation runs.
- The chat history keeps the question as typed.

**Evaluation** records the glossary each run used (`use_glossary` and the full list of terms in the run config). `glossary: false`, `--no-glossary` or the form's checkbox runs without it.

**Demo words** (`backend/demo/glossary.json`) are loaded with the demo company, or with a button when the glossary is empty:
- vacation, time off and vacaciones → PTO, paid time off
- quit → voluntary resignation
- cuentas → beads, devolver → return, recargo → surcharge, urgente → rush

## Measurements

Live runs on a copy of the demo library: `qwen2.5:3b`, hybrid, 5 passages, temperature 0, citation repair on.

| | Passed | Answered | Facts | "Not found" right | Citations to the right file |
|---|---|---|---|---|---|
| Run #5, before | 85% (45/53) | 93% | 86% | 100% | 95% |
| Run #7, with glossary | **89% (47/53)** | 98% | 89% | 100% | 98% |

- **Fixed:** both Spanish questions (days to return beads, the rush surcharge).
- **Broken:** none. All 10 questions whose answer isn't on the shelf still got "not found".
- **Vacation days** is no longer "not found". The model now answers from the PTO table but misreads it ("16 days in years 1–2"; the table says 12), so it still fails. That's a reading error for the next fixes, not a wording one.

## Consequences

- **The demo words were written knowing which questions failed**, so the gain on this golden set is a best case. A glossary only helps with words someone has added. Its value in general is that an admin can fix a "people say X, the documents say Y" gap without editing documents or prompts.
- The glossary isn't versioned like profiles. Changes are in the audit log, and each evaluation run keeps the full list it used. Chat messages don't record which glossary they were asked with.
- A loose entry can change many questions. "time" → "hours" would add text wherever "time" appears. The preview box is there to check an entry first.
- Still failing (6):
  - nickel-free (said "not found")
  - the custom-color email, two wordings (missing detail)
  - the party time (missing detail)
  - vacation days (misread table)
  - custom colors on the operations shelf (answered from the supplier agreement)

  These go to the prompt experiment next.
