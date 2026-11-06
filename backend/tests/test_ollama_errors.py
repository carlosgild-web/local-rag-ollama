"""Ollama's own error reasons reach the chat as readable messages."""

import httpx
import pytest

from app.api.routes.chat import generation_error_detail
from app.llm.ollama_client import OllamaError, _check

_REQUEST = httpx.Request("POST", "http://ollama/api/generate")
# What Ollama 0.40 returned when the model could not fit in free RAM.
_OOM = (
    "llama-server reported out-of-memory during startup: "
    "ggml_backend_cpu_buffer_type_alloc_buffer: failed to allocate buffer of size 194023456"
)


def test_check_raises_with_ollamas_reason():
    response = httpx.Response(500, json={"error": _OOM}, request=_REQUEST)
    with pytest.raises(OllamaError) as caught:
        _check(response, "qwen2.5:3b")
    assert caught.value.status_code == 500
    assert caught.value.out_of_memory
    assert "out-of-memory" in str(caught.value)


def test_check_passes_success_and_handles_non_json_errors():
    _check(httpx.Response(200, json={"response": "ok"}, request=_REQUEST), "m")
    with pytest.raises(OllamaError) as caught:
        _check(httpx.Response(404, text="model not found", request=_REQUEST), "m")
    assert caught.value.reason == "model not found" and not caught.value.out_of_memory


def test_chat_error_messages_say_what_to_do():
    oom = generation_error_detail(OllamaError(500, _OOM, "qwen2.5:3b"), "qwen2.5:3b")
    assert "enough free memory" in oom and "qwen2.5:3b" in oom

    other = generation_error_detail(OllamaError(404, 'model "x" not found', "x"), "x")
    assert 'model "x" not found' in other

    down = generation_error_detail(httpx.ConnectError("refused"), "m")
    assert "Can't reach Ollama" in down
