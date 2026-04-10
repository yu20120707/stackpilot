from app.models.contracts import TriggerCommand
from app.services.command_parser import (
    SUPPORTED_TRIGGER_PHRASES,
    normalize_message_text,
    parse_trigger_command,
)


def test_command_parser_exports_expected_command_slots() -> None:
    assert set(SUPPORTED_TRIGGER_PHRASES) == {
        TriggerCommand.ANALYZE_INCIDENT,
        TriggerCommand.SUMMARIZE_THREAD,
        TriggerCommand.RERUN_ANALYSIS,
    }


def test_command_parser_matches_supported_manual_triggers() -> None:
    assert parse_trigger_command("@bot 分析一下这次故障") is TriggerCommand.ANALYZE_INCIDENT
    assert parse_trigger_command("  帮我总结当前结论  ") is TriggerCommand.SUMMARIZE_THREAD
    assert parse_trigger_command("<at user_id=\"ou_1\">机器人</at> 基于最新信息重试") is TriggerCommand.RERUN_ANALYSIS


def test_command_parser_ignores_unsupported_chatter() -> None:
    assert parse_trigger_command("今天谁值班？") is None


def test_normalize_message_text_removes_feishu_at_tags() -> None:
    assert normalize_message_text("<at user_id=\"ou_1\">机器人</at>   分析一下这次故障") == "分析一下这次故障"
