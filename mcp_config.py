import os
import yaml
from typing import Dict, List, Any
from toolbox_core import ToolboxSyncClient

# This file will manage the MCP Toolbox configuration and client

# Use absolute path or path relative to this file to avoid FileNotFoundError
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_CONFIG_PATH = os.path.join(BASE_DIR, "tools.yaml")

def generate_tools_yaml():
    """Generates a tools.yaml file for the MCP Toolbox."""
    config = {
        "sources": {
            "local-tools": {
                "kind": "python",
                "path": os.path.join(BASE_DIR, "tools/adk_tools.py")
            }
        },
        "tools": {
            "calendar_create_event": {
                "kind": "python-function",
                "source": "local-tools",
                "function": "create_event",
                "description": "Schedule a calendar meeting. Requires start_timestamp, title, and participants."
            },
            "slack_send_message": {
                "kind": "python-function",
                "source": "local-tools",
                "function": "send_message",
                "description": "Send a Slack notification. Requires channel and message."
            },
            "notes_create_note": {
                "kind": "python-function",
                "source": "local-tools",
                "function": "create_note",
                "description": "Create a document/note. Requires title and body."
            }
        },
        "toolsets": {
            "main_toolset": [
                "calendar_create_event",
                "slack_send_message",
                "notes_create_note"
            ]
        }
    }
    
    with open(TOOLS_CONFIG_PATH, "w") as f:
        yaml.dump(config, f)
    print(f"Generated {TOOLS_CONFIG_PATH}")

def get_toolbox_client(url: str = "http://127.0.0.1:5000"):
    """Returns a ToolboxSyncClient connected to the local toolbox server."""
    return ToolboxSyncClient(url)
