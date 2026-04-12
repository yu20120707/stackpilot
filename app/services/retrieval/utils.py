from __future__ import annotations

import re


ASCII_TOKEN_PATTERN = re.compile(r"[a-z0-9_./-]{2,}")
CJK_SEGMENT_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}")
WHITESPACE_PATTERN = re.compile(r"\s+")
STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "into",
    "after",
    "before",
    "then",
    "when",
    "http",
    "https",
    "service",
}


def extract_terms(text: str) -> set[str]:
    normalized = text.lower()
    terms = {
        token
        for token in ASCII_TOKEN_PATTERN.findall(normalized)
        if token not in STOP_WORDS
    }

    for segment in CJK_SEGMENT_PATTERN.findall(normalized):
        terms.add(segment)
        if len(segment) > 2:
            for index in range(len(segment) - 1):
                terms.add(segment[index : index + 2])

    return {term for term in terms if term.strip()}


def build_snippet(content: str, best_term: str) -> str:
    squashed = WHITESPACE_PATTERN.sub(" ", content).strip()
    if not squashed:
        return ""

    if not best_term:
        return squashed[:160]

    normalized_squashed = squashed.lower()
    index = normalized_squashed.find(best_term.lower())
    if index < 0:
        return squashed[:160]

    start = max(0, index - 40)
    end = min(len(squashed), index + len(best_term) + 80)
    snippet = squashed[start:end].strip()

    if start > 0:
        snippet = f"...{snippet}"
    if end < len(squashed):
        snippet = f"{snippet}..."

    return snippet
