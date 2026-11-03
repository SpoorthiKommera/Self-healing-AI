import logging
import random
import httpx
from datetime import datetime
from typing import List, Dict, Any
import os

# This file contains ADK-compatible tool functions

logger = logging.getLogger("adk_tools")

# --- Calendar Tool ---
def create_event(start_timestamp: str = None, title: str = "Meeting", participants: List[str] = None, **kwargs):
    """
    Schedule a calendar meeting.
    
    Args:
        start_timestamp: ISO 8601 formatted string (e.g. 2026-04-05T10:00:00)
        title: Meeting title
        participants: List of attendee emails
    """
    # Self-healing logic: if start_timestamp is missing but meeting_time is present (legacy)
    if not start_timestamp and "meeting_time" in kwargs:
        start_timestamp = kwargs["meeting_time"]
        logger.warning(f"Healed: mapped legacy 'meeting_time' to 'start_timestamp': {start_timestamp}")

    if not start_timestamp:
        raise ValueError(f"Missing required field 'start_timestamp'. Received: {list(kwargs.keys())}")

    event_id = f"evt_{random.randint(10000, 99999)}"
    return {
        "event_id": event_id,
        "status": "success",
        "details": {"title": title, "start": start_timestamp}
    }

# --- Slack Tool ---
async def send_message(channel: str, message: str):
    """Send a Slack notification."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    
    if webhook_url:
        payload = {"text": message}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code == 200:
                return {"ok": True, "mode": "real"}
            else:
                raise RuntimeError(f"Slack error: {resp.status_code}")
    else:
        logger.info(f"[MOCK SLACK] {channel}: {message}")
        return {"ok": True, "mode": "mock"}

# --- Notes Tool ---
def create_note(title: str, body: str):
    """Create a document/note."""
    note_id = f"note_{random.randint(1000, 9999)}"
    return {"note_id": note_id, "title": title, "status": "created"}
