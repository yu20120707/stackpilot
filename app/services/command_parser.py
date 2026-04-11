import re

from app.models.contracts import TriggerCommand

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
}

MENTION_TAG_PATTERN = re.compile(r"<at\b[^>]*>.*?</at>", re.IGNORECASE)
MENTION_PLACEHOLDER_PATTERN = re.compile(r"@_user_\d+", re.IGNORECASE)
PLAIN_AT_MENTION_PATTERN = re.compile(r"(?<!\S)@[^\s]+")
WHITESPACE_PATTERN = re.compile(r"\s+")


def parse_trigger_command(message_text: str) -> TriggerCommand | None:
    normalized_text = normalize_message_text(message_text)

    if not normalized_text:
        return None

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


def is_follow_up_trigger(trigger_command: TriggerCommand) -> bool:
    return trigger_command in {
        TriggerCommand.SUMMARIZE_THREAD,
        TriggerCommand.RERUN_ANALYSIS,
    }
