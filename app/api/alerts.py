from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from app.core.logging import get_logger

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

logger = get_logger(__name__)
ALERT_WEBHOOK_SECRET_HEADER = "X-Alert-Webhook-Secret"


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def handle_alert_events(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    expected_secret = _extract_expected_webhook_secret(request)
    if expected_secret and not _has_valid_webhook_secret(request, expected_secret):
        logger.info("Alert webhook rejected: invalid_webhook_secret")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_webhook_secret")

    payload = await _load_request_payload(request)
    if payload is None:
        logger.info("Alert webhook rejected: invalid_alert_payload")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_alert_payload")

    services = getattr(request.app.state, "services", None)
    alert_ingress_flow = getattr(services, "alert_ingress_flow", None)
    if alert_ingress_flow is None:
        logger.warning("Alert webhook accepted but no alert ingress flow is configured.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="alert_ingress_service_unavailable",
        )

    background_tasks.add_task(alert_ingress_flow.process_webhook, payload)
    logger.info("Alert webhook accepted and queued for background processing.")
    return {"code": 0, "msg": "accepted"}


async def _load_request_payload(request: Request) -> dict[str, Any] | None:
    try:
        payload = await request.json()
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    return payload


def _extract_expected_webhook_secret(request: Request) -> str | None:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        return None

    configured_secret = getattr(settings, "alert_webhook_secret", None)
    return _pick_non_empty_string(configured_secret)


def _has_valid_webhook_secret(request: Request, expected_secret: str) -> bool:
    provided_secret = _pick_non_empty_string(request.headers.get(ALERT_WEBHOOK_SECRET_HEADER))
    if provided_secret is None:
        return False

    return provided_secret == expected_secret


def _pick_non_empty_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    return normalized or None
