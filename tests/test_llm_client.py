import json

import httpx
import pytest

from app.clients.llm_client import LLMClient, LLMClientConfig


def build_client(handler) -> LLMClient:  # noqa: ANN001
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, timeout=30)
    return LLMClient(
        LLMClientConfig(
            base_url="https://example.test/v1",
            api_key="test-key",
            model="gpt-5",
            timeout_seconds=30,
        ),
        http_client=http_client,
    )


@pytest.mark.anyio
async def test_llm_client_returns_non_stream_content_without_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "pong",
                        }
                    }
                ]
            },
        )

    client = build_client(handler)
    try:
        result = await client.generate_structured_summary(
            system_prompt="Reply with exactly: pong",
            user_prompt="",
        )
    finally:
        await client.aclose()

    assert result == "pong"


@pytest.mark.anyio
async def test_llm_client_falls_back_to_sse_when_non_stream_content_is_empty() -> None:
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        calls.append(payload)

        if payload.get("stream") is True:
            sse_body = (
                'data: {"choices":[{"delta":{"content":"po"}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"ng"}}]}\n\n'
                'data: [DONE]\n\n'
            )
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                content=sse_body.encode(),
            )

        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                        }
                    }
                ]
            },
        )

    client = build_client(handler)
    try:
        result = await client.generate_structured_summary(
            system_prompt="Reply with exactly: pong",
            user_prompt="",
        )
    finally:
        await client.aclose()

    assert result == "pong"
    assert len(calls) == 2
    assert calls[0].get("stream") is None
    assert calls[1]["stream"] is True
