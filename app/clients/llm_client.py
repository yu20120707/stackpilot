from __future__ import annotations

from dataclasses import dataclass

import httpx


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
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        }
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
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMInvalidResponseError("response did not contain chat completion content") from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMInvalidResponseError("response content was empty")

        return content.strip()

    async def aclose(self) -> None:
        await self.http_client.aclose()
