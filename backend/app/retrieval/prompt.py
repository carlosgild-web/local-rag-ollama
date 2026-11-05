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
    return f"{instructions}\n\nContext:\n{context}\n\nQuestion: {question}\n\nAnswer:"
