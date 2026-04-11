from __future__ import annotations

from dataclasses import dataclass
import re

import httpx


PULL_REQUEST_URL_PATTERN = re.compile(
    r"^https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/pull/(?P<number>\d+)(?:[/?#].*)?$",
    re.IGNORECASE,
)


@dataclass(slots=True)
class GitHubReviewClientConfig:
    base_url: str = "https://api.github.com"
    token: str | None = None
    timeout_seconds: int = 20


@dataclass(slots=True)
class GitHubPullRequestRef:
    owner: str
    repo: str
    number: int
    html_url: str


class GitHubReviewClient:
    def __init__(
        self,
        config: GitHubReviewClientConfig | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config or GitHubReviewClientConfig()
        self.http_client = http_client or httpx.AsyncClient(timeout=self.config.timeout_seconds)

    def parse_pull_request_url(self, pull_request_url: str) -> GitHubPullRequestRef | None:
        match = PULL_REQUEST_URL_PATTERN.fullmatch(pull_request_url.strip())
        if match is None:
            return None

        return GitHubPullRequestRef(
            owner=match.group("owner"),
            repo=match.group("repo"),
            number=int(match.group("number")),
            html_url=pull_request_url.strip(),
        )

    async def fetch_pull_request_diff(self, pull_request_url: str) -> str | None:
        ref = self.parse_pull_request_url(pull_request_url)
        if ref is None:
            return None

        response = await self.http_client.get(
            f"{self.config.base_url.rstrip('/')}/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}",
            headers=self._build_diff_headers(),
        )
        if response.is_error:
            return None

        diff_text = response.text.strip()
        return diff_text or None

    async def publish_issue_comment(
        self,
        *,
        pull_request_url: str,
        body: str,
    ) -> str | None:
        ref = self.parse_pull_request_url(pull_request_url)
        if ref is None:
            return None

        response = await self.http_client.post(
            f"{self.config.base_url.rstrip('/')}/repos/{ref.owner}/{ref.repo}/issues/{ref.number}/comments",
            headers=self._build_json_headers(),
            json={"body": body},
        )
        if response.is_error:
            return None

        try:
            payload = response.json()
            html_url = payload.get("html_url")
        except ValueError:
            return None

        if isinstance(html_url, str) and html_url.strip():
            return html_url.strip()
        return f"{pull_request_url}#issuecomment"

    async def aclose(self) -> None:
        await self.http_client.aclose()

    def _build_diff_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github.v3.diff"}
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        return headers

    def _build_json_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        }
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        return headers
