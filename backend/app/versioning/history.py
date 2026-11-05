"""Chat history: sessions, messages, the sources behind each answer
(invariant 5), and feedback. The single writer for these tables."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ChatSession, Feedback, Message, MessageSource, utcnow
from app.versioning.service import ConflictError, NotFoundError

TITLE_MAX_CHARS = 60


@dataclass
class SourceRef:
    chunk_id: int
    rank: int
    score: float


def create_session(db: Session, first_question: str) -> ChatSession:
    title = " ".join(first_question.split())[:TITLE_MAX_CHARS] or "New chat"
    session = ChatSession(title=title)
    db.add(session)
    db.commit()
    return session


def get_session(db: Session, session_id: int) -> ChatSession:
    session = db.get(ChatSession, session_id)
    if session is None:
        raise NotFoundError(f"session {session_id} not found")
    return session


def list_sessions(
    db: Session, *, limit: int = 50, offset: int = 0
) -> list[tuple[ChatSession, int]]:
    """Newest first, each with its message count."""
    rows = db.execute(
        select(ChatSession, func.count(Message.id))
        .outerjoin(Message, Message.session_id == ChatSession.id)
        .group_by(ChatSession.id)
        .order_by(ChatSession.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [(session, count) for session, count in rows]


def add_message(
    db: Session,
    session_id: int,
    role: str,
    content: str,
    *,
    rag_profile_id: int | None = None,
    sources: list[SourceRef] | None = None,
) -> Message:
    get_session(db, session_id)
    message = Message(
        session_id=session_id, role=role, content=content, rag_profile_id=rag_profile_id
    )
    db.add(message)
    db.flush()
    for source in sources or []:
        db.add(
            MessageSource(
                message_id=message.id,
                chunk_id=source.chunk_id,
                rank=source.rank,
                score=source.score,
            )
        )
    db.commit()
    return message


def set_feedback(
    db: Session, message_id: int, *, thumbs_up: bool, comment: str | None = None
) -> Feedback:
    """One feedback row per message; a second call replaces the first."""
    message = db.get(Message, message_id)
    if message is None:
        raise NotFoundError(f"message {message_id} not found")
    if message.role != "assistant":
        raise ConflictError("feedback is only accepted on assistant messages")

    feedback = db.execute(
        select(Feedback).where(Feedback.message_id == message_id)
    ).scalar_one_or_none()
    if feedback is None:
        feedback = Feedback(message_id=message_id, thumbs_up=thumbs_up, comment=comment)
        db.add(feedback)
    else:
        feedback.thumbs_up = thumbs_up
        feedback.comment = comment
        feedback.created_at = utcnow()
    db.commit()
    return feedback
