"""Points each [n] citation at the passage that supports the claim (decision 0020).

The 3B chat model often states the right fact and cites the wrong number:
in the Phase 7 baseline, 7 of 16 failed questions were right answers with a
citation to the wrong document. This runs after the answer is written and
changes only the citation markers, never the words.

A claim is the text between one run of markers ("[1][3]", "[2, 4]") and the
previous one, so "The price is $1.60. This is in [1]." checks "$1.60"
against [1]. Each passage is scored on the claim's anchors: numbers (worth
3, since a wrong document rarely has the same figures) and content words.
A marker is changed only when the evidence is clear:
- every cited number is out of range, or the model cited a section title
  such as "[4. Separation of Employment]" -> the best passage;
- the cited passages miss a number the claim states and another passage
  has all of them -> that passage;
- no number decides, but another passage shares clearly more words -> that
  passage;
- in a run of several markers, one that scores under half of the best cited
  one is dropped;
- a sentence after the last marker that cites nothing gets the one passage
  that clearly supports it: a shared number or 3 shared words, and no tie.
Anything less clear is left as the model wrote it.
"""

import re
from dataclasses import dataclass, field

from app.retrieval.prompt import NOT_FOUND_PHRASE
from app.retrieval.textnorm import normalize

_MARKER = r"\[\d+(?:\s*,\s*\d+)*\]"  # [1] or [1, 3]
_SECTION_LABEL = r"\[\d+\.\s+[^\[\]\n]+\]"  # [4. Separation of Employment]
_RUN = re.compile(rf"(?:\s*(?:{_MARKER}|{_SECTION_LABEL}))+")
_NUMERIC_MARKER = re.compile(_MARKER)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_WORD = re.compile(r"[a-zñ]+")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# Words that say nothing about which passage a claim came from.
_STOPWORD_TEXT = """
    about above according after again also although another answer based because been
    before being below between both cited context could document documents does doing down
    during each from further have having here information into itself just more most must
    only other over same says should source sources specifically stated states such than
    that their them then there these they this those through under until very were what
    when where which while with would your yours como esta este para pero porque segun
    sobre tiene todo todos usted
"""
_STOPWORDS = frozenset(_STOPWORD_TEXT.split())

NUMBER_WEIGHT = 3
WORD_MARGIN = 2  # extra shared words another passage needs to win on words alone


@dataclass
class CitationRepair:
    text: str
    changes: list[tuple[str, str]] = field(default_factory=list)  # (before, after)

    @property
    def changed(self) -> bool:
        return bool(self.changes)


@dataclass
class _Anchors:
    numbers: set[str]
    words: set[str]


def _numbers(text: str) -> set[str]:
    """Numbers without thousands separators or trailing decimal zeros:
    "1,200" -> "1200", "$1.60" -> "1.6". A lone decimal comma counts as a point."""
    found = set()
    for raw in _NUMBER.findall(text):
        value = raw.replace(",", "") if re.fullmatch(r"\d{1,3}(?:,\d{3})+", raw) else raw
        value = value.replace(",", ".")
        if "." in value:
            value = value.rstrip("0").rstrip(".")
        found.add(value)
    return found


def _anchors(text: str) -> _Anchors:
    norm = normalize(text)
    words = {w for w in _WORD.findall(norm) if len(w) >= 4 and w not in _STOPWORDS}
    return _Anchors(numbers=_numbers(norm), words=words)


def _score(claim: _Anchors, passage: _Anchors) -> int:
    return NUMBER_WEIGHT * len(claim.numbers & passage.numbers) + len(claim.words & passage.words)


def _choose(claim: _Anchors, cited: list[int], passages: list[_Anchors]) -> list[int]:
    """The 1-based passage numbers this claim should cite. Returns `cited`
    unchanged when the evidence isn't clear."""
    scores = [_score(claim, p) for p in passages]
    best = max(range(len(passages)), key=lambda i: (scores[i], -i)) + 1
    best_score = scores[best - 1]
    valid = [n for n in cited if 1 <= n <= len(passages)]
    if not valid:
        return [best] if best_score > 0 else cited
    if best_score == 0:
        return valid

    covered = set().union(*(passages[n - 1].numbers for n in valid)) & claim.numbers
    best_numbers = passages[best - 1].numbers & claim.numbers
    if claim.numbers and len(covered) < len(claim.numbers) and best_numbers == claim.numbers:
        return [best]

    if best_numbers <= covered:
        best_words = len(claim.words & passages[best - 1].words)
        cited_words = max(len(claim.words & passages[n - 1].words) for n in valid)
        if best_words >= cited_words + WORD_MARGIN and cited_words * 2 <= best_words:
            return [best]

    cited_best = max(scores[n - 1] for n in valid)
    return [n for n in valid if scores[n - 1] * 2 >= cited_best]


def _cite_uncited(
    text: str, passages: list[_Anchors], *, after_marker: bool
) -> tuple[str, list[tuple[str, str]]]:
    """Adds [n] to sentences with no citation when one passage clearly wins.
    Right after a marker, the first piece continues the cited sentence
    ("[2] states that ...") and is left alone."""
    pieces = _SENTENCE_END.split(text)
    gaps = _SENTENCE_END.findall(text)
    changes = []
    for i, sentence in enumerate(pieces):
        if i == 0 and after_marker:
            continue
        claim = _anchors(sentence)
        ranked = sorted(
            ((_score(claim, p), -n) for n, p in enumerate(passages, start=1)), reverse=True
        )
        top = ranked[0][0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0
        if top < NUMBER_WEIGHT or top == runner_up:
            continue
        marker = f"[{-ranked[0][1]}]"
        body = sentence.rstrip()
        trail = sentence[len(body) :]
        if body[-1] in ".!?":
            pieces[i] = f"{body[:-1]} {marker}{body[-1]}{trail}"
        else:
            pieces[i] = f"{body} {marker}{trail}"
        changes.append(("", marker))
    out = [pieces[0]]
    for gap, piece in zip(gaps, pieces[1:], strict=True):
        out += [gap, piece]
    return "".join(out), changes


def _format(numbers: list[int]) -> str:
    return "".join(f"[{n}]" for n in dict.fromkeys(numbers))


def repair_citations(answer: str, passages: list[str]) -> CitationRepair:
    """`passages` are the texts sent to the model, in prompt order ([1] first)."""
    if not passages or NOT_FOUND_PHRASE in answer.lower():
        return CitationRepair(answer)
    anchored = [_anchors(p) for p in passages]
    out: list[str] = []
    changes: list[tuple[str, str]] = []
    start = 0
    for match in _RUN.finditer(answer):
        claim_text = answer[start : match.start()]
        run = match.group(0)
        cited = [
            int(n) for marker in _NUMERIC_MARKER.findall(run) for n in re.findall(r"\d+", marker)
        ]
        claim = _anchors(claim_text)
        chosen = _choose(claim, cited, anchored) if claim.numbers or claim.words else cited
        if chosen != cited or (
            chosen and len(_NUMERIC_MARKER.findall(run)) < len(re.findall(r"\[", run))
        ):
            # A changed citation, or a section label replaced by its number.
            new_run = run[: len(run) - len(run.lstrip())] + _format(chosen)
            if chosen:
                changes.append((run.strip(), new_run.strip()))
                run = new_run
        out.append(claim_text + run)
        start = match.end()
    tail, added = _cite_uncited(answer[start:], anchored, after_marker=start > 0)
    out.append(tail)
    return CitationRepair("".join(out), changes + added)
