from dotenv import load_dotenv
import os

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"

# Use /tmp for Cloud Run (read-only filesystem except /tmp)
DB_DIR = os.getenv("DB_DIR", "/tmp")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_DIR}/healing.db")

# Real Slack webhook URL (optional — falls back to mock if empty)
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

PORT = int(os.getenv("PORT", "8080"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
MAX_RETRIES = 3
RETRY_DELAY_SEC = 1

# Available tools the planner can use
AVAILABLE_TOOLS = {
    "calendar.list_meetings": {
        "description": "List existing meetings for a given date to check availability before scheduling",
        "required_params": ["date"],
        "param_formats": {"date": "ISO 8601 date (e.g. 2026-04-08)"},
    },
    "calendar.create_event": {
        "description": "Schedule a calendar meeting (ALWAYS call list_meetings first to check availability)",
        "required_params": ["meeting_time", "title", "participants"],
        "param_formats": {"meeting_time": "ISO 8601 (e.g. 2026-04-05T10:00:00)"},
    },
    "slack.send_message": {
        "description": "Send a Slack notification",
        "required_params": ["channel", "message"],
        "param_formats": {"channel": "#channel-name"},
    },
    "notes.create_note": {
        "description": "Create a document/note",
        "required_params": ["title", "body"],
        "param_formats": {},
    },
}
