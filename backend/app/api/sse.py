"""Server-sent events helpers."""

import json
from collections.abc import AsyncIterator, Iterator

import anyio
from starlette.concurrency import run_in_threadpool

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

_DONE = object()


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def drive_sync_stream(iterator: Iterator[str]) -> AsyncIterator[str]:
    """Streams a blocking generator from a worker thread, and always closes it.

    Starlette's own handling of sync iterators just drops the generator when
    the client disconnects, so its `finally` blocks (e.g. saving a partial
    answer) would only run whenever it gets garbage-collected. Here the
    close runs shielded from the disconnect's cancellation.
    """
    try:
        while True:
            item = await run_in_threadpool(next, iterator, _DONE)
            if item is _DONE:
                break
            yield item
    finally:
        with anyio.CancelScope(shield=True):
            await run_in_threadpool(iterator.close)
