import logging
from typing import Dict

logger = logging.getLogger("tools.notes")

_store: Dict[str, str] = {}


async def create_note(params: dict) -> dict:
    """Mock Notes API."""
    title = params.get("title", "Untitled")
    body = params.get("body", "")
    note_id = f"note_{abs(hash(title)) % 100000:05d}"
    _store[note_id] = body
    logger.info(f"Note created: {note_id} - '{title}'")
    return {"note_id": note_id, "title": title, "status": "created"}
