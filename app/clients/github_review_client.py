from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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


@dataclass(slots=True)
class GitHubIssueComment:
    comment_id: int
    html_url: str
    body: str
    author_login: str | None = None
    created_at: datetime | None = None


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
    ) -> GitHubIssueComment | None:
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
        except ValueError:
            return None

        return self._parse_issue_comment_payload(payload, fallback_url=f"{pull_request_url}#issuecomment")

    async def list_issue_comments(
        self,
        *,
        pull_request_url: str,
    ) -> list[GitHubIssueComment]:
        ref = self.parse_pull_request_url(pull_request_url)
        if ref is None:
            return []

        response = await self.http_client.get(
            f"{self.config.base_url.rstrip('/')}/repos/{ref.owner}/{ref.repo}/issues/{ref.number}/comments",
            headers=self._build_json_headers(),
        )
        if response.is_error:
            return []

        try:
            payload = response.json()
        except ValueError:
            return []
        if not isinstance(payload, list):
            return []

        comments: list[GitHubIssueComment] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            parsed_comment = self._parse_issue_comment_payload(
                item,
                fallback_url=f"{pull_request_url}#issuecomment",
            )
            if parsed_comment is not None:
                comments.append(parsed_comment)
        return comments

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

    def _parse_issue_comment_payload(
        self,
        payload: dict[str, object],
        *,
        fallback_url: str,
    ) -> GitHubIssueComment | None:
        comment_id = payload.get("id")
        if not isinstance(comment_id, int) or comment_id < 1:
            return None

        html_url = payload.get("html_url")
        normalized_html_url = html_url.strip() if isinstance(html_url, str) and html_url.strip() else fallback_url
        body = payload.get("body")
        normalized_body = body if isinstance(body, str) else ""

        user_payload = payload.get("user")
        author_login = None
        if isinstance(user_payload, dict):
            login = user_payload.get("login")
            if isinstance(login, str) and login.strip():
                author_login = login.strip()

        created_at = self._parse_timestamp(payload.get("created_at"))
        return GitHubIssueComment(
            comment_id=comment_id,
            html_url=normalized_html_url,
            body=normalized_body,
            author_login=author_login,
            created_at=created_at,
        )

    def _parse_timestamp(self, raw_value: object) -> datetime | None:
        if not isinstance(raw_value, str) or not raw_value.strip():
            return None
        try:
            return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError:
            return None
