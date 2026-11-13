"""LLM-judged faithfulness: does the answer only say what the sources say?

The judge is a local Ollama chat model (the run's chat model unless another
is named), so nothing leaves the machine. A small model is a weak judge:
treat the score as a hint to read the answer, not as ground truth
(decision 0019). The verdict is one word, which even a 3B model follows.
"""

import re

from app.retrieval.prompt import format_context
from app.retrieval.retrieve import RetrievedChunk

VERDICTS = {"yes": 1.0, "partly": 0.5, "no": 0.0}

JUDGE_INSTRUCTIONS = """You check whether an answer is supported by numbered sources.
Read the sources and the answer. Ignore the [n] markers and the wording; check the facts.
Reply with one word first: YES if every fact in the answer is stated in the sources, PARTLY if some are, NO if none are.
Then give one short sentence naming any fact that is not in the sources."""  # noqa: E501

_VERDICT = re.compile(r"\b(yes|partly|no)\b", re.IGNORECASE)


def judge_prompt(chunks: list[RetrievedChunk], answer: str) -> str:
    return (
        f"{JUDGE_INSTRUCTIONS}\n\nSources:\n{format_context(chunks)}\n\n"
        f"Answer to check:\n{answer.strip()}\n\nVerdict:"
    )


def parse_verdict(reply: str) -> tuple[float | None, str]:
    """(score, note). The first YES/PARTLY/NO word decides; a reply without
    one scores None, so it's left out of the average instead of counted as 0."""
    text = reply.strip()
    match = _VERDICT.search(text)
    if match is None:
        return None, text[:500]
    return VERDICTS[match.group(1).lower()], text[:500]
