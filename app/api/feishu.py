import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request

from app.core.logging import get_logger
from app.models.contracts import (
    CallbackHandlingStatus,
    CallbackResult,
    FeishuVerificationRequest,
    NormalizedFeishuMessageEvent,
    TriggerCommand,
)
from app.services.command_parser import parse_trigger_command

router = APIRouter(prefix="/api/feishu", tags=["feishu"])

logger = get_logger(__name__)
SUPPORTED_EVENT_TYPES = {"im.message.receive_v1", "message"}


@router.post("/events")
async def handle_feishu_events(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    payload = await _load_request_payload(request)
    if payload is None:
        logger.info("Feishu callback ignored: callback_parse_failed")
        return _safe_ignore_response("callback_parse_failed")

    expected_token = _extract_expected_verification_token(request)
    if expected_token and not _has_valid_callback_token(payload, expected_token):
        logger.info("Feishu callback ignored: invalid_verification_token")
        return _safe_ignore_response("invalid_verification_token")

    verification_request = _parse_verification_request(payload)
    if verification_request is not None:
        logger.info("Feishu callback verification challenge accepted.")
        return {"challenge": verification_request.challenge}

    normalized_event = _parse_message_event(payload)
    if normalized_event is None:
        logger.info(
            "Feishu callback ignored: unsupported_event event_type=%s",
            _extract_event_type(payload),
        )
        return _safe_ignore_response("unsupported_event")

    if _is_direct_message(payload):
        logger.info(
            "Feishu callback ignored: unsupported_context message_id=%s",
            normalized_event.message_id,
        )
        return _safe_ignore_response("unsupported_context")

    trigger_command = parse_trigger_command(normalized_event.message_text)
    if trigger_command is None:
        logger.info(
            "Feishu callback ignored: unsupported_message message_id=%s text=%r",
            normalized_event.message_id,
            normalized_event.message_text,
        )
        return _safe_ignore_response("unsupported_message")

    result = CallbackResult(
        status=CallbackHandlingStatus.ACCEPTED,
        trigger_command=trigger_command,
        message_event=normalized_event,
    )
    logger.info(
        "Feishu callback accepted: command=%s chat_id=%s thread_id=%s message_id=%s",
        trigger_command.value,
        normalized_event.chat_id,
        normalized_event.thread_id,
        normalized_event.message_id,
    )
    _queue_live_flow(
        request=request,
        background_tasks=background_tasks,
        trigger_command=trigger_command,
        normalized_event=normalized_event,
    )
    return {"code": 0, "msg": "ok", "data": result.model_dump(mode="json")}


async def _load_request_payload(request: Request) -> dict[str, Any] | None:
    try:
        payload = await request.json()
    except Exception:
        logger.warning("Failed to parse Feishu callback payload as JSON.")
        return None

    if not isinstance(payload, dict):
        logger.warning("Feishu callback payload is not a JSON object.")
        return None

    return payload


def _parse_verification_request(payload: dict[str, Any]) -> FeishuVerificationRequest | None:
    if payload.get("type") != "url_verification":
        return None

    challenge = payload.get("challenge")
    if not isinstance(challenge, str) or not challenge.strip():
        logger.warning("Feishu verification payload missing challenge.")
        return None

    token = _extract_callback_token(payload)

    return FeishuVerificationRequest(challenge=challenge, token=token)


def _parse_message_event(payload: dict[str, Any]) -> NormalizedFeishuMessageEvent | None:
    event_type = _extract_event_type(payload)
    if event_type not in SUPPORTED_EVENT_TYPES:
        return None

    event = payload.get("event")
    if not isinstance(event, dict):
        return None

    message = event.get("message")
    if not isinstance(message, dict):
        return None

    message_text = _extract_message_text(message.get("content"))
    if not message_text:
        return None

    chat_id = _pick_non_empty_string(message.get("chat_id"))
    message_id = _pick_non_empty_string(message.get("message_id"))
    sender_id = _extract_sender_id(event.get("sender"))

    if not all((chat_id, message_id, sender_id)):
        return None

    thread_id = (
        _pick_non_empty_string(message.get("thread_id"))
        or _pick_non_empty_string(message.get("root_id"))
        or _pick_non_empty_string(message.get("parent_id"))
        or message_id
    )

    sender_name = _extract_sender_name(event.get("sender"))
    mentions_bot = _detect_bot_mention(message, message_text)
    event_time = _extract_event_time(payload, event, message)

    return NormalizedFeishuMessageEvent(
        chat_id=chat_id,
        message_id=message_id,
        thread_id=thread_id,
        sender_id=sender_id,
        sender_name=sender_name,
        message_text=message_text,
        mentions_bot=mentions_bot,
        event_time=event_time,
    )


def _extract_event_type(payload: dict[str, Any]) -> str | None:
    header = payload.get("header")
    if isinstance(header, dict):
        event_type = header.get("event_type")
        if isinstance(event_type, str) and event_type.strip():
            return event_type.strip()

    payload_type = payload.get("type")
    if isinstance(payload_type, str) and payload_type.strip():
        return payload_type.strip()

    return None


def _extract_message_text(content: Any) -> str | None:
    if isinstance(content, dict):
        text = content.get("text")
        return _pick_non_empty_string(text)

    if isinstance(content, str):
        stripped = content.strip()
        if not stripped:
            return None

        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                return stripped
            if isinstance(decoded, dict):
                return _pick_non_empty_string(decoded.get("text")) or stripped

        return stripped

    return None


def _extract_sender_id(sender: Any) -> str | None:
    if not isinstance(sender, dict):
        return None

    sender_id = sender.get("sender_id")
    if isinstance(sender_id, dict):
        for key in ("open_id", "user_id", "union_id"):
            value = _pick_non_empty_string(sender_id.get(key))
            if value:
                return value

    return _pick_non_empty_string(sender.get("sender_id"))


def _extract_sender_name(sender: Any) -> str | None:
    if not isinstance(sender, dict):
        return None

    for key in ("sender_name", "name"):
        value = _pick_non_empty_string(sender.get(key))
        if value:
            return value

    return None


def _detect_bot_mention(message: dict[str, Any], message_text: str) -> bool:
    mentions = message.get("mentions")
    if isinstance(mentions, list) and len(mentions) > 0:
        return True

    return "@".encode().decode() in message_text or "<at" in message_text.lower()


def _extract_event_time(payload: dict[str, Any], event: dict[str, Any], message: dict[str, Any]) -> datetime:
    candidate = (
        _pick_non_empty_string(message.get("create_time"))
        or _pick_non_empty_string(event.get("event_time"))
        or _pick_non_empty_string(payload.get("event_time"))
    )

    header = payload.get("header")
    if candidate is None and isinstance(header, dict):
        candidate = _pick_non_empty_string(header.get("create_time"))

    if candidate is None:
        return datetime.now(timezone.utc)

    if candidate.isdigit():
        timestamp = int(candidate)
        if timestamp > 10_000_000_000:
            return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

    try:
        return datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("Failed to parse Feishu event time '%s'; using current time.", candidate)
        return datetime.now(timezone.utc)


def _is_direct_message(payload: dict[str, Any]) -> bool:
    event = payload.get("event")
    if not isinstance(event, dict):
        return False

    message = event.get("message")
    if not isinstance(message, dict):
        return False

    chat_type = _pick_non_empty_string(message.get("chat_type"))
    return chat_type == "p2p"


def _pick_non_empty_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    return normalized or None


def _safe_ignore_response(reason: str) -> dict[str, Any]:
    result = CallbackResult(
        status=CallbackHandlingStatus.IGNORED,
        reason=reason,
    )
    return {"code": 0, "msg": "ok", "data": result.model_dump(mode="json")}


def _extract_expected_verification_token(request: Request) -> str | None:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        return None

    configured_token = getattr(settings, "feishu_verification_token", None)
    return _pick_non_empty_string(configured_token)


def _has_valid_callback_token(payload: dict[str, Any], expected_token: str) -> bool:
    callback_token = _extract_callback_token(payload)
    if callback_token is None:
        logger.warning("Feishu callback payload did not contain a verification token.")
        return False

    if callback_token != expected_token:
        logger.warning("Feishu callback token mismatch.")
        return False

    return True


def _extract_callback_token(payload: dict[str, Any]) -> str | None:
    header = payload.get("header")
    if isinstance(header, dict):
        token = _pick_non_empty_string(header.get("token"))
        if token:
            return token

    return _pick_non_empty_string(payload.get("token"))


def _queue_live_flow(
    *,
    request: Request,
    background_tasks: BackgroundTasks,
    trigger_command: TriggerCommand,
    normalized_event: NormalizedFeishuMessageEvent,
) -> None:
    services = getattr(request.app.state, "services", None)
    live_flow = getattr(services, "feishu_live_flow", None)
    if live_flow is None:
        logger.warning("Feishu callback accepted but no live flow service is configured.")
        return

    background_tasks.add_task(
        live_flow.process_trigger,
        trigger_command=trigger_command,
        trigger_event=normalized_event,
    )
