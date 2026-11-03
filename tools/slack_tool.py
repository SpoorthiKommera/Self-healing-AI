import json
import logging
from typing import Dict

import httpx

import config

logger = logging.getLogger("tools.slack")


async def send_message(params: dict) -> dict:
    """Slack integration: uses real webhook if configured, else mock."""
    channel = params.get("channel", "#general")
    message = params.get("message", "")

    if config.SLACK_WEBHOOK_URL:
        return await _send_real(channel, message)
    else:
        return _send_mock(channel, message)


async def _send_real(channel: str, message: str) -> dict:
    """Send via real Slack Incoming Webhook."""
    payload = {
        "text": message,
        "username": "Self-Healing Agent",
        "icon_emoji": ":robot_face:",
    }

    # Incoming webhooks post to a fixed channel, but we log the intended one
    logger.info(f"[Slack REAL] Sending to webhook (intended {channel}): {message}")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            config.SLACK_WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
        )

    if resp.status_code == 200 and resp.text == "ok":
        logger.info(f"[Slack REAL] Message delivered successfully")
        return {"ok": True, "channel": channel, "message": message, "mode": "webhook"}
    else:
        error_msg = f"Slack webhook error: {resp.status_code} {resp.text}"
        logger.error(f"[Slack REAL] {error_msg}")
        raise RuntimeError(error_msg)


def _send_mock(channel: str, message: str) -> dict:
    """Mock Slack when no webhook is configured."""
    logger.info(f"[Slack MOCK] -> {channel}: {message}")
    return {
        "ok": True,
        "channel": channel,
        "ts": "1712300000.000100",
        "message": message,
        "mode": "mock",
    }
