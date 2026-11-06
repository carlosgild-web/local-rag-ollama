"""Builds the grounded, cited RAG prompt from retrieved chunks.

PLAN.md section 6, "Answer rule": answer only from context, otherwise say
the answer is not found in the documents. Citations are mandatory
(CLAUDE.md invariant 6).
"""

from app.retrieval.retrieve import RetrievedChunk

NOT_FOUND_PHRASE = "not found in the documents"

SYSTEM_INSTRUCTIONS = f"""You are a helpful assistant that answers questions using ONLY the numbered context below. Follow these rules strictly:

1. Answer only using information present in the context. Do not use outside knowledge.
2. Cite every claim with the bracketed source number(s) it came from, e.g. [1] or [1][3].
3. If the context does not contain the answer, respond with exactly: "{NOT_FOUND_PHRASE}" and nothing else."""  # noqa: E501


def _source_label(chunk: RetrievedChunk, index: int) -> str:
    location = f"page {chunk.page}" if chunk.page else (chunk.heading or "")
    suffix = f" ({location})" if location else ""
    return f"[{index}] {chunk.filename}{suffix}"


def format_context(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"{_source_label(chunk, i)}\n{chunk.text}" for i, chunk in enumerate(chunks, start=1)
    )


def format_sources(chunks: list[RetrievedChunk]) -> str:
    return "\n".join(_source_label(chunk, i) for i, chunk in enumerate(chunks, start=1))


def build_prompt(
    question: str, chunks: list[RetrievedChunk], system_instructions: str | None = None
) -> str:
    """`system_instructions` comes from the active rag_profile; profiles are
    validated to keep the not-found rule (app/versioning/profiles.py)."""
    instructions = system_instructions or SYSTEM_INSTRUCTIONS
    context = format_context(chunks)
    return (
        f"{instructions}\n\nContext:\n{context}\n\nQuestion: {question}\n\n"
        f"{citation_reminder(len(chunks))}\n\nAnswer:"
    )


def citation_reminder(source_count: int) -> str:
    """Repeated right before "Answer:", where a small model attends most. In
    the 2026-11-06 end-to-end test qwen2.5:3b left out or misnumbered 36% of
    its citations with the rules only at the top. Part of the prompt code,
    not the profile, so it also applies to existing profile versions."""
    allowed = "[1]" if source_count == 1 else f"[1] to [{source_count}]"
    return (
        "Reminder: answer only from the context above. End every sentence with the number "
        "of the source it came from, in square brackets, for example: "
        '"Orders ship in 5 business days [2]." '
        f"Only use the source numbers shown in the context ({allowed}). "
        f'If the context does not contain the answer, reply exactly: "{NOT_FOUND_PHRASE}"'
    )
