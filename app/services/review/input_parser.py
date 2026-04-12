from __future__ import annotations

from dataclasses import dataclass
import re

from app.models.contracts import ReviewSourceType


FENCED_BLOCK_PATTERN = re.compile(
    r"```(?:diff|patch)?\s*(?P<body>.*?)```",
    re.IGNORECASE | re.DOTALL,
)
GITHUB_PULL_REQUEST_URL_PATTERN = re.compile(
    r"https?://github\.com/[\w.-]+/[\w.-]+/pull/\d+(?:[/?#][^\s]*)?",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ReviewInput:
    source_type: ReviewSourceType
    source_ref: str
    raw_input: str


def extract_review_input(message_text: str) -> ReviewInput | None:
    patch_text = extract_patch_text(message_text)
    if patch_text is not None:
        return ReviewInput(
            source_type=ReviewSourceType.PATCH_TEXT,
            source_ref="inline_patch",
            raw_input=patch_text,
        )

    pr_url = extract_github_pull_request_url(message_text)
    if pr_url is not None:
        return ReviewInput(
            source_type=ReviewSourceType.GITHUB_PR,
            source_ref=pr_url,
            raw_input=message_text.strip(),
        )

    return None


def extract_github_pull_request_url(message_text: str) -> str | None:
    match = GITHUB_PULL_REQUEST_URL_PATTERN.search(message_text)
    if match is None:
        return None
    return match.group(0).strip()


def extract_patch_text(message_text: str) -> str | None:
    for match in FENCED_BLOCK_PATTERN.finditer(message_text):
        block = match.group("body").strip()
        if _looks_like_patch(block):
            return block

    first_diff_index = message_text.find("diff --git ")
    if first_diff_index >= 0:
        candidate = message_text[first_diff_index:].strip()
        if _looks_like_patch(candidate):
            return candidate

    stripped = message_text.strip()
    if _looks_like_patch(stripped):
        return stripped

    return None


def has_github_pull_request_url(message_text: str) -> bool:
    return extract_github_pull_request_url(message_text) is not None


def has_patch_text(message_text: str) -> bool:
    return extract_patch_text(message_text) is not None


def _looks_like_patch(value: str) -> bool:
    if not value:
        return False

    return (
        "diff --git " in value
        or ("@@ " in value and "+++ " in value and "--- " in value)
        or ("\n+++ " in value and "\n--- " in value)
    )
