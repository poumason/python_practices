"""
LiteLLM Webhook Receiver

Receives and processes webhook events sent by the LiteLLM proxy.

Configure LiteLLM to send webhooks by adding to litellm_config.yaml:

  general_settings:
    alerting: ["webhook"]
    alerting_threshold: 300
    webhook_url: "http://localhost:8888/webhook"
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="LiteLLM Webhook Receiver", version="1.0.0")


# --- Pydantic models for LiteLLM webhook payloads ---

class WebhookEvent(BaseModel):
    event: Optional[str] = None
    event_group: Optional[str] = None
    event_message: Optional[str] = None
    token: Optional[str] = None
    spend: Optional[float] = None
    max_budget: Optional[float] = None
    user_id: Optional[str] = None
    team_id: Optional[str] = None
    key_alias: Optional[str] = None
    projected_exceeded_date: Optional[str] = None
    projected_spend: Optional[float] = None


class SpendPayload(BaseModel):
    spend: Optional[float] = None
    max_budget: Optional[float] = None
    token: Optional[str] = None
    user: Optional[str] = None
    team: Optional[str] = None


class AlertPayload(BaseModel):
    type: Optional[str] = None
    event: Optional[str] = None
    message: Optional[str] = None
    level: Optional[str] = None  # "Low", "Medium", "High", "Critical"
    webhook_event: Optional[WebhookEvent] = None
    spend_payload: Optional[SpendPayload] = None


# --- Event handlers ---

def handle_budget_alert(event: WebhookEvent, raw: dict) -> None:
    logger.warning(
        "[BUDGET ALERT] user=%s team=%s spend=%.4f max=%.4f projected=%s",
        event.user_id,
        event.team_id,
        event.spend or 0,
        event.max_budget or 0,
        event.projected_exceeded_date,
    )


def handle_llm_exception(event: WebhookEvent, raw: dict) -> None:
    logger.error(
        "[LLM EXCEPTION] message=%s token=%s",
        event.event_message,
        event.token,
    )


def handle_cooldown(event: WebhookEvent, raw: dict) -> None:
    logger.warning("[COOLDOWN] message=%s", event.event_message)


def handle_outage(event: WebhookEvent, raw: dict) -> None:
    logger.critical("[OUTAGE] message=%s", event.event_message)


def handle_spend_report(event: WebhookEvent, raw: dict) -> None:
    logger.info(
        "[SPEND REPORT] spend=%.4f max=%.4f user=%s team=%s",
        event.spend or 0,
        event.max_budget or 0,
        event.user_id,
        event.team_id,
    )


def handle_new_model(event: WebhookEvent, raw: dict) -> None:
    logger.info("[NEW MODEL] message=%s", event.event_message)


def handle_default(event: WebhookEvent, raw: dict) -> None:
    logger.info("[EVENT:%s] message=%s", event.event or "unknown", event.event_message)


EVENT_HANDLERS = {
    "budget_crossed": handle_budget_alert,
    "projected_limit_exceeded": handle_budget_alert,
    "llm_exceptions": handle_llm_exception,
    "cooldown_model": handle_cooldown,
    "outage_alerts": handle_outage,
    "region_outage_alerts": handle_outage,
    "spend_reports": handle_spend_report,
    "new_model_added": handle_new_model,
}


# --- Routes ---

@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "time": datetime.utcnow().isoformat()})


@app.post("/webhook")
async def receive_webhook(request: Request) -> JSONResponse:
    """Main webhook endpoint — accepts all LiteLLM alert/event payloads."""
    try:
        body: dict[str, Any] = await request.json()
    except Exception as exc:
        logger.error("Failed to parse webhook body: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    logger.debug("Raw webhook payload:\n%s", json.dumps(body, indent=2, default=str))

    # Extract the inner webhook_event if present (LiteLLM wraps it)
    raw_event: dict = body.get("webhook_event") or body
    event = WebhookEvent.model_validate(raw_event)

    event_key = event.event or body.get("type") or body.get("event") or "unknown"
    handler = EVENT_HANDLERS.get(event_key, handle_default)
    handler(event, body)

    return JSONResponse({"status": "received", "event": event_key})


@app.post("/webhook/completion")
async def receive_completion_event(request: Request) -> JSONResponse:
    """
    Optional endpoint for completion-level events if you configure
    LiteLLM custom logger callbacks to POST here instead of using
    the built-in alerting webhook.
    """
    try:
        body: dict[str, Any] = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    model = body.get("model", "unknown")
    usage = body.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", 0)

    logger.info(
        "[COMPLETION] model=%s prompt=%d completion=%d total=%d",
        model,
        prompt_tokens,
        completion_tokens,
        total_tokens,
    )

    return JSONResponse({"status": "received"})


# --- Entry point ---

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8888, log_level="info")
