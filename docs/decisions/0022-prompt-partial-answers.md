# 0022: A "partial answers" rule in the prompt (and a rejected "keep the details" rule)

**Status:** accepted (2026-11-14)

## Context

After the citation repair (0020) and the glossary (0021), 47 of 53 golden-set questions passed (run #7). The remaining failures happen while the 3B model writes the answer:
- "not found" for nickel-free antique bronze, although the FAQ entry was retrieved
- details left out: the custom-color email, the party time
- the PTO table misread for "vacation days"
- custom colors on the operations shelf answered from the supplier agreement

Prompt changes are risky with this model. In decision 0007 a longer citation reminder took facts from 6/6 to 0/6. So each variant got one short extra rule, and the rule was set in advance: **keep a variant only if passed goes up, every "not found" question still gets "not found", and nothing that passes breaks.**

## Measurements

Each variant ran as its own profile: `default` v2 plus one rule, `qwen2.5:3b`, temperature 0, hybrid, 5 passages, citation repair and glossary on. Each was compared with run #7 on the same 53 questions.

| | Passed | Facts | "Not found" right | Wording groups | Fixed | Broken |
|---|---|---|---|---|---|---|
| #7, rules 1–3 | 89% (47) | 89% | 100% | 50% | | |
| #8, A: "4. If the context answers part of the question, answer that part." | **91% (48)** | 91% | 100% | 75% | vacation days | none |
| #9, B: "4. Give the exact numbers, dates, times, prices and contact details (emails, phone numbers) the context states for the question." | 87% (46) | 86% | 100% | 75% | vacation days, nickel-free | $18 shipping cost, Strategic Partner terms, carrier to Canada |

## Decision

- **Rule A is kept.** The live `default` profile became v3 with it (`POST /api/profiles`, audited), and `SYSTEM_INSTRUCTIONS` includes it, so new installs start with the same four rules.
- **Rule B is rejected.** It fixed two questions and broke three: the Strategic Partner terms became "not found", and the carrier answer was just "[2]". It never brought back the custom-color email either.
- The portal's language rule ("Write the answer in Spanish.") now takes the next free number (5 after these four rules) instead of a fixed "4.". Unnumbered custom prompts get it without a number.

## Consequences

- **A's gain is one question, within run-to-run noise.** Identical runs have differed by one answer before (the face shield, decision 0020). It is kept because it met every condition and broke nothing, not because +1 is proven. The final Phase 7 run measures it again.
- **A didn't fix nickel-free, the question it was aimed at.** Its one gain was vacation days, which now reads the PTO table correctly (12 / 16 / 20).
- Five questions still fail: the party time, the custom-color email (two wordings), nickel-free, and custom colors on the operations shelf. They look like the limits of a 3B model. The 7B/8B models in the plan should do better but don't fit this laptop's 7.2 GB RAM (decision 0004). They're left as known limits for this hardware.
