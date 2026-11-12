"""Chat (PLAN.md section 8): streamed answers over server-sent events, plus
session history and feedback.

`POST /chat` event stream, in order:
  session  {"session_id", "user_message_id"}
  sources  [{"rank", "chunk_id", "document_id", "version_id", "filename", ...}]
  token    {"text"}              (repeated)
  done     {"message_id", "rag_profile_id", "not_found"}
  error    {"detail"}            (instead of done, if generation fails)
"""

import logging
from collections.abc import Iterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import DbDep, RuntimeDep
from app.api.routes.retrieval import chunk_out, resolve_collection
from app.api.schemas import (
    Channel,
    ChatIn,
    FeedbackIn,
    FeedbackOut,
    FeedbackSummaryOut,
    MessageOut,
    SessionOut,
    SessionSummary,
    SourceOut,
)
from app.api.sse import SSE_HEADERS, drive_sync_stream, sse
from app.core.runtime import Runtime
from app.db.models import Chunk, Document, DocumentVersion, Feedback, Message, MessageSource
from app.llm.ollama_client import OllamaError
from app.retrieval.citations import citation_status
from app.retrieval.prompt import NOT_FOUND_PHRASE, with_answer_language
from app.retrieval.qa import AnswerContext, prepare_context, prepare_context_many
from app.versioning import history, profiles, service
from app.versioning.history import SourceRef

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


@router.post(
    "/chat",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE stream"}},
)
def chat(db: DbDep, runtime: RuntimeDep, body: ChatIn):
    """Answers from the documents only, with citations, streamed as SSE.
    Retrieval runs before the stream opens, so an unreachable Ollama or an
    unknown collection/session is a normal HTTP error."""
    settings = runtime.settings
    profile = profiles.get_active_profile(
        db, settings, body.profile or profiles.DEFAULT_PROFILE_NAME
    )
    existing = history.get_session(db, body.session_id) if body.session_id is not None else None
    # A follow-up stays in the channel its conversation started in.
    channel = existing.channel if existing else body.channel
    instructions = with_answer_language(profile.system_prompt, body.answer_language)

    if channel == "intranet":
        session = existing or history.create_session(db, body.question, channel="intranet")
        shelves = service.portal_collections(db)
        context = (
            prepare_context_many(
                db,
                body.question,
                collections=shelves,
                settings=settings,
                embedding_client_for=runtime.embedding_client_for,
                vector_store=runtime.vector_store,
                top_k=profile.retrieval_top_k,
                system_instructions=instructions,
            )
            if shelves
            else None
        )
    else:
        collection = resolve_collection(
            db,
            runtime,
            body.collection_id,
            session_collection_id=existing.collection_id if existing else None,
        )
        if existing is None:
            session = history.create_session(db, body.question, collection_id=collection.id)
        else:
            session = existing
            if session.collection_id != collection.id:  # remember the shelf for follow-ups
                session.collection_id = collection.id
                db.commit()

        context = prepare_context(
            db,
            body.question,
            collection=collection,
            settings=settings,
            embedding_client=runtime.embedding_client_for(collection.embedding_model),
            vector_store=runtime.vector_store,
            top_k=profile.retrieval_top_k,
            system_instructions=instructions,
        )
    user_message = history.add_message(db, session.id, "user", body.question)

    stream = _answer_stream(
        runtime,
        context,
        session_id=session.id,
        user_message_id=user_message.id,
        profile_id=profile.id,
        chat_model=profile.chat_model,
        temperature=profile.temperature,
    )
    return StreamingResponse(
        drive_sync_stream(stream), media_type="text/event-stream", headers=SSE_HEADERS
    )


def _answer_stream(
    runtime: Runtime,
    context: AnswerContext | None,
    *,
    session_id: int,
    user_message_id: int,
    profile_id: int,
    chat_model: str,
    temperature: float,
) -> Iterator[str]:
    yield sse("session", {"session_id": session_id, "user_message_id": user_message_id})

    chunks = context.chunks if context else []
    yield sse(
        "sources",
        [chunk_out(rank, c).model_dump(exclude={"text"}) for rank, c in enumerate(chunks, 1)],
    )

    parts: list[str] = []
    saved = False

    def save() -> int:
        nonlocal saved
        saved = True
        with runtime.session_factory() as db:
            message = history.add_message(
                db,
                session_id,
                "assistant",
                "".join(parts),
                rag_profile_id=profile_id,
                sources=[
                    SourceRef(chunk_id=c.chunk_id, rank=rank, score=c.score)
                    for rank, c in enumerate(chunks, start=1)
                ],
            )
            return message.id

    try:
        if context is None:
            parts.append(NOT_FOUND_PHRASE)
            yield sse("token", {"text": NOT_FOUND_PHRASE})
        else:
            llm = runtime.llm_client_for(chat_model)
            for piece in llm.stream_generate(
                context.prompt,
                temperature=temperature,
                num_ctx=runtime.settings.ollama_num_ctx,
            ):
                parts.append(piece)
                yield sse("token", {"text": piece})
        message_id = save()
        yield sse(
            "done",
            {
                "message_id": message_id,
                "rag_profile_id": profile_id,
                "not_found": context is None,
                "citation_status": citation_status("".join(parts), len(chunks)),
            },
        )
    except Exception as exc:
        logger.exception("chat generation failed", extra={"session_id": session_id})
        yield sse("error", {"detail": generation_error_detail(exc, chat_model)})
    finally:
        # Client went away mid-answer: keep what was generated, with its sources.
        if not saved and parts:
            save()


def generation_error_detail(exc: Exception, chat_model: str) -> str:
    """A message the chat can show as is: what went wrong and what to do."""
    if isinstance(exc, OllamaError) and exc.out_of_memory:
        return (
            f"Ollama doesn't have enough free memory to load the chat model ({chat_model}). "
            "Close other programs (Docker Desktop and browsers use a lot) and ask again, "
            "or switch to a smaller chat model."
        )
    if isinstance(exc, OllamaError):
        return f"Ollama couldn't answer with {chat_model}: {exc.reason}"
    if isinstance(exc, httpx.TransportError):
        return "Can't reach Ollama. Check that it is running, then ask again."
    return f"The answer failed ({type(exc).__name__}). Check the server log for details."


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    channel: Channel = "admin",
    q: Annotated[str | None, Query(max_length=200, description="Text in a chat")] = None,
):
    """The console's chats by default; `channel=intranet` lists the
    employee portal's. `q` keeps only chats with that text."""
    return [
        SessionSummary(
            id=s.id,
            title=s.title,
            created_at=s.created_at,
            message_count=count,
            collection_id=s.collection_id,
            channel=s.channel,
        )
        for s, count in history.list_sessions(db, limit=limit, offset=offset, channel=channel, q=q)
    ]


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(db: DbDep, session_id: int):
    session = history.get_session(db, session_id)
    messages = (
        db.execute(select(Message).where(Message.session_id == session.id).order_by(Message.id))
        .scalars()
        .all()
    )
    message_ids = [m.id for m in messages]

    source_rows = db.execute(
        select(MessageSource, Chunk, Document)
        .join(Chunk, Chunk.id == MessageSource.chunk_id)
        .join(DocumentVersion, DocumentVersion.id == Chunk.version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(MessageSource.message_id.in_(message_ids))
        .order_by(MessageSource.rank)
    ).all()
    sources: dict[int, list[SourceOut]] = {}
    for source, chunk, document in source_rows:
        sources.setdefault(source.message_id, []).append(
            SourceOut(
                rank=source.rank,
                chunk_id=source.chunk_id,
                score=source.score,
                document_id=document.id,
                filename=document.filename,
                page=chunk.page,
                heading=chunk.heading,
            )
        )
    feedback = {
        f.message_id: f
        for f in db.execute(select(Feedback).where(Feedback.message_id.in_(message_ids)))
        .scalars()
        .all()
    }

    return SessionOut(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        collection_id=session.collection_id,
        channel=session.channel,
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                rag_profile_id=m.rag_profile_id,
                created_at=m.created_at,
                sources=sources.get(m.id, []),
                feedback=FeedbackOut.model_validate(feedback[m.id]) if m.id in feedback else None,
                citation_status=(
                    citation_status(m.content, len(sources.get(m.id, [])))
                    if m.role == "assistant"
                    else None
                ),
            )
            for m in messages
        ],
    )


@router.get("/feedback/summary", response_model=FeedbackSummaryOut)
def feedback_summary(db: DbDep, limit: Annotated[int, Query(ge=1, le=50)] = 5):
    """How answers were rated, and the latest "not helpful" ones to look at."""
    return history.feedback_summary(db, limit=limit)


@router.post("/messages/{message_id}/feedback", response_model=FeedbackOut)
def set_feedback(db: DbDep, message_id: int, body: FeedbackIn):
    return history.set_feedback(db, message_id, thumbs_up=body.thumbs_up, comment=body.comment)
