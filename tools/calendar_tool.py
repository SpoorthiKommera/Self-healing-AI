import logging
import random

logger = logging.getLogger("tools.calendar")

# Global state for simulation
_FAILURE_MODE = False


def enable_failure_mode():
    global _FAILURE_MODE
    _FAILURE_MODE = True
    logger.warning("Calendar tool FAILURE MODE enabled")


def disable_failure_mode():
    global _FAILURE_MODE
    _FAILURE_MODE = False
    logger.info("Calendar tool failure mode disabled")


def is_failure_mode():
    return _FAILURE_MODE


def transform_to_broken_schema(params: dict) -> dict:
    """Simulate an upstream API schema change: rename time fields and break format."""
    broken = dict(params)
    for field in ("meeting_time", "start_timestamp"):
        if field in broken:
            try:
                from datetime import datetime as _dt
                dt = _dt.fromisoformat(broken[field])
                # Preserve date context but break the format
                broken["time"] = dt.strftime("%b %d at %I:%M %p")  # e.g. "Apr 08 at 11:00 AM"
            except (ValueError, TypeError):
                broken["time"] = "10:00 AM"
            broken.pop(field)
    return broken


async def list_meetings(params: dict) -> dict:
    """Return meetings for a given date. Simulates busy slots for 2026-04-08."""
    date = params.get("date", "")
    logger.info(f"Calendar.list_meetings called for date: {date}")

    if date == "2026-04-08":
        meetings = [
            {"title": "Sprint Standup", "start": "2026-04-08T09:00:00", "end": "2026-04-08T09:30:00"},
            {"title": "Design Review", "start": "2026-04-08T10:00:00", "end": "2026-04-08T11:00:00"},
            {"title": "Lunch with Client", "start": "2026-04-08T12:00:00", "end": "2026-04-08T13:00:00"},
            {"title": "Team Retro", "start": "2026-04-08T15:00:00", "end": "2026-04-08T16:00:00"},
        ]
    else:
        meetings = []

    logger.info(f"Calendar.list_meetings returning {len(meetings)} meetings for {date}")
    return {"date": date, "meetings": meetings, "count": len(meetings)}


async def create_event(params: dict) -> dict:
    """
    Calendar API that accepts meeting_time or start_timestamp.
    Raises ValueError if neither is present (simulates schema validation).
    """
    data = params if isinstance(params, dict) else {}

    meeting_time = data.get("meeting_time") or data.get("start_timestamp")
    title = data.get("title")
    participants = data.get("participants", [])

    if not meeting_time:
        received_fields = list(data.keys())
        error_msg = (
            f"Schema validation error: missing required field 'meeting_time'. "
            f"Received fields: {received_fields}"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    event_id = f"evt_{random.randint(10000, 99999)}"
    logger.info(f"Calendar.create_event SUCCESS with meeting_time: {meeting_time}")

    return {
        "event_id": event_id,
        "status": "success",
        "details": {"title": title, "start": meeting_time},
    }
