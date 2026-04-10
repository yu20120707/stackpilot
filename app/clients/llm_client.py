from __future__ import annotations

from dataclasses import dataclass

import httpx
import json


class LLMClientError(Exception):
    """Base exception for LLM adapter failures."""


class LLMTimeoutError(LLMClientError):
    """Raised when the upstream LLM request times out."""


class LLMRequestError(LLMClientError):
    """Raised when the upstream LLM request fails."""


class LLMInvalidResponseError(LLMClientError):
    """Raised when the upstream LLM response is malformed."""


@dataclass(slots=True)
class LLMClientConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 30


class LLMClient:
    def __init__(
        self,
        config: LLMClientConfig,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.http_client = http_client or httpx.AsyncClient(timeout=config.timeout_seconds)

    async def generate_structured_summary(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        payload = self._build_payload(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = await self.http_client.post(
                f"{self.config.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("request timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMRequestError("request failed") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMInvalidResponseError("response did not contain valid JSON") from exc

        content = self._extract_content_from_response(data)
        if content:
            return content

        # Some OpenAI-compatible gateways only emit usable content in SSE mode.
        return await self._generate_via_stream(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

    def _build_payload(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        return {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        }

    def _extract_content_from_response(self, data: dict) -> str | None:
        try:
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMInvalidResponseError("response did not contain chat completion content") from exc

        if not isinstance(content, str) or not content.strip():
            return None

        return content.strip()

    async def _generate_via_stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        payload = self._build_payload(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        payload["stream"] = True
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        try:
            async with self.http_client.stream(
                "POST",
                f"{self.config.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                chunks: list[str] = []
                async for line in response.aiter_lines():
                    normalized = line.strip()
                    if not normalized or not normalized.startswith("data:"):
                        continue

                    data_line = normalized.removeprefix("data:").strip()
                    if data_line == "[DONE]":
                        break

                    try:
                        event = json.loads(data_line)
                    except json.JSONDecodeError:
                        continue

                    delta = (
                        event.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content")
                    )
                    if isinstance(delta, str) and delta:
                        chunks.append(delta)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("request timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMRequestError("request failed") from exc

        content = "".join(chunks).strip()
        if not content:
            raise LLMInvalidResponseError("response content was empty")

        return content

    async def aclose(self) -> None:
        await self.http_client.aclose()
