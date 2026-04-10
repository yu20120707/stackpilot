import re

from app.models.contracts import TriggerCommand

SUPPORTED_TRIGGER_PHRASES: dict[TriggerCommand, tuple[str, ...]] = {
    TriggerCommand.ANALYZE_INCIDENT: (
        "分析一下这次故障",
        "分析这次故障",
    ),
    TriggerCommand.SUMMARIZE_THREAD: (
        "帮我总结当前结论",
        "总结当前结论",
    ),
    TriggerCommand.RERUN_ANALYSIS: (
        "基于最新信息重试",
        "基于最新信息重新分析",
        "重新分析一下",
    ),
}

MENTION_TAG_PATTERN = re.compile(r"<at\b[^>]*>.*?</at>", re.IGNORECASE)
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
    without_mentions = MENTION_TAG_PATTERN.sub(" ", message_text)
    collapsed = WHITESPACE_PATTERN.sub(" ", without_mentions)
    return collapsed.strip()


def collapse_for_matching(text: str) -> str:
    normalized = normalize_message_text(text)
    return normalized.replace(" ", "")


def is_follow_up_trigger(trigger_command: TriggerCommand) -> bool:
    return trigger_command in {
        TriggerCommand.SUMMARIZE_THREAD,
        TriggerCommand.RERUN_ANALYSIS,
    }
