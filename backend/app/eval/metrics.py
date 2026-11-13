"""Scoring of one evaluation case, and the totals of a run (decision 0019).

Pure functions over plain values, so they're tested without a database.

Retrieval is scored on the document level: a hit is any chunk from one of
the case's expected files. That's what a reader checks when they open a
citation, and it doesn't break when a reindex renumbers the chunks.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.retrieval.citations import cited_numbers
from app.retrieval.prompt import NOT_FOUND_PHRASE
from app.retrieval.textnorm import normalize

HIT_K = 5  # hit rate@5 (PLAN.md Phase 7)


def is_not_found(answer: str) -> bool:
    return NOT_FOUND_PHRASE in normalize(answer)


def missing_facts(answer: str, facts: Sequence[Sequence[str]]) -> list[list[str]]:
    """The fact groups the answer has none of the alternatives of."""
    text = normalize(answer)
    return [list(group) for group in facts if not any(normalize(alt) in text for alt in group)]


def first_relevant_rank(filenames: Sequence[str], expected: Iterable[str]) -> int | None:
    """1-based rank of the first chunk from an expected file."""
    wanted = set(expected)
    for rank, filename in enumerate(filenames, start=1):
        if filename in wanted:
            return rank
    return None


def cited_filenames(answer: str, sent_filenames: Sequence[str]) -> list[str]:
    """The files the answer's [n] markers point at, in order, once each.
    Numbers without a source are left out (citation_status reports them)."""
    cited: list[str] = []
    for number in cited_numbers(answer):
        if 1 <= number <= len(sent_filenames):
            filename = sent_filenames[number - 1]
            if filename not in cited:
                cited.append(filename)
    return cited


def citations_on_target(cited: Sequence[str], expected: Iterable[str]) -> bool:
    """At least one citation, and every cited file is an expected one."""
    wanted = set(expected)
    return bool(cited) and all(filename in wanted for filename in cited)


@dataclass
class CaseScore:
    """What `summarize` needs of one case. EvalResult rows have these fields."""

    expect_not_found: bool
    expected_sources: list[str]
    required_facts: list[list[str]]
    variant_group: str | None = None
    first_relevant_rank: int | None = None
    answer: str | None = None
    not_found: bool | None = None
    missing_facts: list[list[str]] | None = None
    cited_sources: list[str] | None = None
    faithfulness: float | None = None
    passed: bool | None = None
    retrieval_ms: int = 0
    answer_ms: int | None = None
    error: str | None = None


def case_passed(case: CaseScore, *, with_answers: bool) -> bool | None:
    """Without answers only retrieval is judged (hit@5); a "not found" case
    can't pass or fail on retrieval alone. With answers:
    - a "not found" case passes when the answer says "not found";
    - any other case passes when it isn't "not found", has every required
      fact, and (if sources are listed) cites only expected files."""
    if case.error:
        return False
    if not with_answers:
        if case.expect_not_found or not case.expected_sources:
            return None
        return case.first_relevant_rank is not None and case.first_relevant_rank <= HIT_K
    if case.expect_not_found:
        return bool(case.not_found)
    if case.not_found:
        return False
    if case.missing_facts:
        return False
    if case.expected_sources:
        return citations_on_target(case.cited_sources or [], case.expected_sources)
    return True


def _rate(values: list[bool]) -> float | None:
    return sum(values) / len(values) if values else None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def summarize(cases: Sequence[CaseScore], *, with_answers: bool) -> dict:
    """The run's totals. A rate is None when no case could be measured for it
    (e.g. no answers were generated), never 0, so "not measured" stays distinct."""
    ok = [c for c in cases if not c.error]
    answerable = [c for c in ok if not c.expect_not_found and c.expected_sources]
    ranks = [c.first_relevant_rank for c in answerable]
    metrics: dict = {
        "cases": len(cases),
        "errors": len(cases) - len(ok),
        "answerable": len(answerable),
        "traps": sum(c.expect_not_found for c in ok),
        "hit_rate_at_5": _rate([r is not None and r <= HIT_K for r in ranks]),
        "hit_rate_at_1": _rate([r == 1 for r in ranks]),
        "mrr": _mean([1 / r if r else 0.0 for r in ranks]),
        "retrieval_ms": _mean([c.retrieval_ms for c in ok]),
        "pass_rate": _rate([c.passed for c in cases if c.passed is not None]),
    }
    groups: dict[str, list[CaseScore]] = {}
    for case in cases:
        if case.variant_group:
            groups.setdefault(case.variant_group, []).append(case)
    # A wording group passes only when every wording of the question passes.
    metrics["variant_groups"] = sum(len(g) > 1 for g in groups.values())
    metrics["variant_rate"] = _rate(
        [
            all(c.passed for c in g)
            for g in groups.values()
            if len(g) > 1 and all(c.passed is not None for c in g)
        ]
    )
    if not with_answers:
        return metrics

    asked = [c for c in ok if not c.expect_not_found]
    answered = [c for c in asked if c.not_found is False]
    traps = [c for c in ok if c.expect_not_found]
    judged = [c.faithfulness for c in ok if c.faithfulness is not None]
    metrics.update(
        {
            # Questions with an answer that got one (not a "not found").
            "answered_rate": _rate([c.not_found is False for c in asked]),
            # Of those with required facts: every fact is in the answer.
            "facts_rate": _rate([not c.missing_facts for c in asked if c.required_facts]),
            # Questions whose answer isn't there that got "not found".
            "trap_rate": _rate([bool(c.not_found) for c in traps]),
            # Answers whose citations all point at an expected file.
            "citation_rate": _rate(
                [
                    citations_on_target(c.cited_sources or [], c.expected_sources)
                    for c in answered
                    if c.expected_sources
                ]
            ),
            "faithfulness": _mean(judged),
            "judged": len(judged),
            "answer_ms": _mean([c.answer_ms for c in ok if c.answer_ms is not None]),
        }
    )
    return metrics
