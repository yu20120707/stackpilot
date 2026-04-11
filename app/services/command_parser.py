import re

from app.models.contracts import TriggerCommand
from app.services.review.input_parser import has_github_pull_request_url, has_patch_text

SUPPORTED_TRIGGER_PHRASES: dict[TriggerCommand, tuple[str, ...]] = {
    TriggerCommand.ANALYZE_INCIDENT: (
        "分析一下这次故障",
        "分析这次故障",
        "分析一下故障原因",
        "分析故障原因",
        "分析一下报警原因",
        "分析报警原因",
        "分析一下问题在哪",
        "分析问题在哪",
        "分析一下问题在哪里",
        "分析问题在哪里",
        "帮我分析一下报警原因",
        "帮我分析一下故障原因",
        "帮我看下故障原因",
        "帮我看看问题在哪",
    ),
    TriggerCommand.SUMMARIZE_THREAD: (
        "帮我总结当前结论",
        "总结当前结论",
        "帮我总结一下当前结论",
        "总结一下当前结论",
        "帮我总结一下",
        "总结一下",
    ),
    TriggerCommand.RERUN_ANALYSIS: (
        "基于最新信息重试",
        "基于最新信息重新分析",
        "重新分析一下",
        "重新分析下",
        "再分析一下",
        "再分析下",
        "重试一下",
    ),
    TriggerCommand.REVIEW_CODE: (
        "帮我cr这个pr",
        "帮我review这个pr",
        "审一下这个pr",
        "审一下这个diff",
        "帮我做代码审查",
        "review this pr",
        "review this diff",
        "code review this pr",
    ),
}

MENTION_TAG_PATTERN = re.compile(r"<at\b[^>]*>.*?</at>", re.IGNORECASE)
MENTION_PLACEHOLDER_PATTERN = re.compile(r"@_user_\d+", re.IGNORECASE)
PLAIN_AT_MENTION_PATTERN = re.compile(r"(?<!\S)@[^\s]+")
WHITESPACE_PATTERN = re.compile(r"\s+")
APPROVE_ACTION_PATTERN = re.compile(
    r"^(?:确认|批准|执行)(?:执行)?动作\s+([a-z0-9_-]+)$",
    re.IGNORECASE,
)
REVIEW_FEEDBACK_PATTERN = re.compile(
    r"^(?:(采纳|接受|忽略|驳回))(?:审查|建议|finding)?\s+([a-z0-9_-]+)$",
    re.IGNORECASE,
)
PROMOTE_CANONICAL_PATTERN = re.compile(
    r"^(?:沉淀|推广|提升为)(?:规范|技能|canonical)?\s+([a-z0-9_-]+)$",
    re.IGNORECASE,
)


def parse_trigger_command(message_text: str) -> TriggerCommand | None:
    normalized_text = normalize_message_text(message_text)

    if not normalized_text:
        return None

    if extract_approved_action_id(normalized_text) is not None:
        return TriggerCommand.APPROVE_ACTION

    if extract_review_feedback(normalized_text) is not None:
        return TriggerCommand.REVIEW_FEEDBACK

    if extract_promotion_candidate_id(normalized_text) is not None:
        return TriggerCommand.PROMOTE_CANONICAL

    if _is_code_review_trigger(
        original_text=message_text,
        normalized_text=normalized_text,
    ):
        return TriggerCommand.REVIEW_CODE

    collapsed_text = collapse_for_matching(normalized_text)

    for trigger_command, phrases in SUPPORTED_TRIGGER_PHRASES.items():
        if any(collapse_for_matching(phrase) in collapsed_text for phrase in phrases):
            return trigger_command

    return None


def normalize_message_text(message_text: str) -> str:
    without_tag_mentions = MENTION_TAG_PATTERN.sub(" ", message_text)
    without_placeholder_mentions = MENTION_PLACEHOLDER_PATTERN.sub(" ", without_tag_mentions)
    without_plain_mentions = PLAIN_AT_MENTION_PATTERN.sub(" ", without_placeholder_mentions)
    collapsed = WHITESPACE_PATTERN.sub(" ", without_plain_mentions)
    return collapsed.strip()


def collapse_for_matching(text: str) -> str:
    normalized = normalize_message_text(text)
    return normalized.replace(" ", "")


def extract_approved_action_id(message_text: str) -> str | None:
    normalized = normalize_message_text(message_text)
    match = APPROVE_ACTION_PATTERN.fullmatch(normalized)
    if match is None:
        return None
    return match.group(1).upper()


def extract_review_feedback(message_text: str) -> tuple[str, str] | None:
    normalized = normalize_message_text(message_text)
    match = REVIEW_FEEDBACK_PATTERN.fullmatch(normalized)
    if match is None:
        return None

    verb = match.group(1).lower()
    finding_id = match.group(2).upper()
    if verb in {"采纳", "接受"}:
        return ("accepted", finding_id)
    return ("ignored", finding_id)


def extract_promotion_candidate_id(message_text: str) -> str | None:
    normalized = normalize_message_text(message_text)
    match = PROMOTE_CANONICAL_PATTERN.fullmatch(normalized)
    if match is None:
        return None
    return match.group(1)


def is_follow_up_trigger(trigger_command: TriggerCommand) -> bool:
    return trigger_command in {
        TriggerCommand.SUMMARIZE_THREAD,
        TriggerCommand.RERUN_ANALYSIS,
    }


def _is_code_review_trigger(*, original_text: str, normalized_text: str) -> bool:
    if not (has_github_pull_request_url(original_text) or has_patch_text(original_text)):
        return False

    collapsed_text = collapse_for_matching(normalized_text)
    phrases = SUPPORTED_TRIGGER_PHRASES.get(TriggerCommand.REVIEW_CODE, ())
    if any(collapse_for_matching(phrase) in collapsed_text for phrase in phrases):
        return True

    return any(
        token in collapsed_text
        for token in (
            "cr",
            "review",
            "代码审查",
            "codereview",
        )
    )
