import anyio

from app.api.routes.chat import _answer_stream
from app.api.sse import drive_sync_stream, sse
from app.db.models import Message
from app.retrieval.qa import AnswerContext
from app.versioning import history, profiles


def test_sse_format():
    assert sse("token", {"text": "hé"}) == 'event: token\ndata: {"text": "hé"}\n\n'


def test_drive_sync_stream_closes_generator_when_consumer_stops_early():
    closed = []

    def numbers():
        try:
            yield from ("a", "b", "c")
        finally:
            closed.append(True)

    async def consume_one():
        stream = drive_sync_stream(numbers())
        first = await anext(stream)
        await stream.aclose()  # what a client disconnect does
        return first

    assert anyio.run(consume_one) == "a"
    assert closed == [True]


def test_answer_stream_saves_partial_answer_when_client_disconnects(runtime):
    runtime.fake_llm._responses.append("one two three four")
    with runtime.session_factory() as db:
        session = history.create_session(db, "q")
        profile = profiles.get_active_profile(db, runtime.settings)
        session_id, profile_id = session.id, profile.id

    stream = _answer_stream(
        runtime,
        AnswerContext(prompt="p", chunks=[]),
        session_id=session_id,
        user_message_id=0,
        profile_id=profile_id,
        chat_model="fake",
        temperature=0.2,
    )
    events = [next(stream) for _ in range(3)]  # session, sources, first token
    assert events[2].startswith("event: token")
    stream.close()

    with runtime.session_factory() as db:
        [message] = db.query(Message).filter(Message.role == "assistant").all()
        assert message.content == "one "
        assert message.rag_profile_id == profile_id
