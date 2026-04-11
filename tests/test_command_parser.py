from app.models.contracts import TriggerCommand
from app.services.command_parser import (
    SUPPORTED_TRIGGER_PHRASES,
    extract_approved_action_id,
    normalize_message_text,
    parse_trigger_command,
)


def test_command_parser_exports_expected_command_slots() -> None:
    assert set(SUPPORTED_TRIGGER_PHRASES) == {
        TriggerCommand.ANALYZE_INCIDENT,
        TriggerCommand.SUMMARIZE_THREAD,
        TriggerCommand.RERUN_ANALYSIS,
        TriggerCommand.REVIEW_CODE,
    }


def test_command_parser_matches_supported_manual_triggers() -> None:
    assert parse_trigger_command("@stackpilot 分析一下这次故障") is TriggerCommand.ANALYZE_INCIDENT
    assert parse_trigger_command("  帮我总结当前结论  ") is TriggerCommand.SUMMARIZE_THREAD
    assert parse_trigger_command("<at user_id=\"ou_1\">机器人</at> 基于最新信息重试") is TriggerCommand.RERUN_ANALYSIS


def test_command_parser_matches_broader_natural_language_triggers() -> None:
    assert parse_trigger_command("@_user_1 分析一下报警原因") is TriggerCommand.ANALYZE_INCIDENT
    assert parse_trigger_command("@stackpilot 分析一下问题在哪") is TriggerCommand.ANALYZE_INCIDENT
    assert parse_trigger_command("@stackpilot 总结一下当前结论") is TriggerCommand.SUMMARIZE_THREAD
    assert parse_trigger_command("@stackpilot 再分析一下") is TriggerCommand.RERUN_ANALYSIS


def test_command_parser_matches_action_approval_commands() -> None:
    assert parse_trigger_command("批准动作 A1") is TriggerCommand.APPROVE_ACTION
    assert parse_trigger_command("@stackpilot 确认动作 a2") is TriggerCommand.APPROVE_ACTION
    assert extract_approved_action_id("执行动作 a3") == "A3"


def test_command_parser_matches_manual_code_review_triggers() -> None:
    assert (
        parse_trigger_command("@stackpilot 帮我 review 这个 PR https://github.com/openai/demo/pull/12")
        is TriggerCommand.REVIEW_CODE
    )
    assert (
        parse_trigger_command(
            "@stackpilot 审一下这个 diff ```diff\n"
            "diff --git a/app/services/tickets.py b/app/services/tickets.py\n"
            "--- a/app/services/tickets.py\n"
            "+++ b/app/services/tickets.py\n"
            "@@ -10,2 +10,4 @@\n"
            "+title = payload.get('title').strip()\n"
            "```"
        )
        is TriggerCommand.REVIEW_CODE
    )


def test_command_parser_ignores_unsupported_chatter() -> None:
    assert parse_trigger_command("今天谁值班？") is None


def test_normalize_message_text_removes_feishu_mentions() -> None:
    assert normalize_message_text("<at user_id=\"ou_1\">机器人</at>   分析一下这次故障") == "分析一下这次故障"
    assert normalize_message_text("@_user_1 分析一下报警原因") == "分析一下报警原因"
    assert normalize_message_text("@stackpilot 分析一下问题在哪") == "分析一下问题在哪"
