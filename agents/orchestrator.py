import asyncio
import json
import logging
import uuid
from typing import Dict, List

from google import genai
from google.genai import types

import config
from models.schemas import WorkflowState, WorkflowStep, WorkflowStatus

logger = logging.getLogger("agents.orchestrator")

# ── Gemini dynamic planning prompt ──────────────────────────────
PLANNING_PROMPT = """\
You are an AI workflow planner. Given a user request, produce a JSON array of \
workflow steps using ONLY these available tools:

{tools_description}

USER REQUEST: "{task}"

Rules:
1. Return ONLY a JSON array (no markdown, no explanation).
2. Each element must have: "tool", "action", "params".
3. "tool" is the part before the dot, "action" is the part after.
4. Fill in realistic parameter values based on the user request.
5. meeting_time MUST be ISO 8601 format like "2026-04-08T14:00:00".
6. Order steps logically.
7. Use 2-5 steps max.
8. CRITICAL: ALWAYS call calendar.list_meetings BEFORE calendar.create_event \
to check availability. Use the date from the user request (default: "2026-04-08").
9. Pick a meeting_time that avoids common business hours conflicts \
(e.g. prefer 11:00, 13:00, or 14:00 slots).
10. After scheduling, notify via slack and create notes.

Example output:
[
  {{"tool": "calendar", "action": "list_meetings", "params": {{"date": "2026-04-08"}}}},
  {{"tool": "calendar", "action": "create_event", "params": {{"meeting_time": "2026-04-08T14:00:00", "title": "Team Sync", "participants": ["alice@co.com"]}}}},
  {{"tool": "slack", "action": "send_message", "params": {{"channel": "#team", "message": "Meeting scheduled"}}}},
  {{"tool": "notes", "action": "create_note", "params": {{"title": "Agenda", "body": "Discussion points"}}}}
]
"""

# ── Fallback templates when Gemini is unavailable ───────────────
FALLBACK_TEMPLATES: Dict[str, List[Dict]] = {
    "schedule_meeting": [
        {
            "tool": "calendar",
            "action": "list_meetings",
            "params": {"date": "2026-04-08"},
        },
        {
            "tool": "calendar",
            "action": "create_event",
            "params": {
                "meeting_time": "2026-04-08T14:00:00",
                "title": "Team Sync",
                "participants": ["alice@co.com", "bob@co.com"],
            },
        },
        {
            "tool": "slack",
            "action": "send_message",
            "params": {
                "channel": "#team",
                "message": "Meeting 'Team Sync' scheduled for Apr 8 at 2 PM (availability confirmed)",
            },
        },
        {
            "tool": "notes",
            "action": "create_note",
            "params": {
                "title": "Team Sync - Agenda",
                "body": "1. Sprint review\n2. Blockers\n3. Next steps",
            },
        },
    ],
}

# Keep a public reference for fix_agent fallback recovery
TASK_TEMPLATES = FALLBACK_TEMPLATES


class OrchestratorAgent:
    """Parses user task -> creates a WorkflowState with ordered steps.
    Uses Gemini for dynamic planning when available, falls back to templates."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if not config.GEMINI_API_KEY:
                raise RuntimeError("GEMINI_API_KEY not set")
            self._client = genai.Client(api_key=config.GEMINI_API_KEY)
        return self._client

    async def parse_task(self, task: str, simulate_failure: bool = True) -> WorkflowState:
        logger.info(f"Parsing task: '{task}' (simulate_failure={simulate_failure})")

        # Try Gemini dynamic planning first
        try:
            step_defs = await self._plan_with_gemini(task)
            logger.info(f"[Orchestrator] Gemini generated {len(step_defs)} steps dynamically")
        except Exception as exc:
            logger.warning(f"[Orchestrator] Gemini planning failed ({exc}), using template fallback")
            step_defs = self._plan_with_templates(task)

        steps = []
        for idx, step_def in enumerate(step_defs):
            steps.append(
                WorkflowStep(
                    id=idx,
                    tool=step_def["tool"],
                    action=step_def["action"],
                    params=dict(step_def["params"]),
                )
            )

        wf = WorkflowState(
            workflow_id=str(uuid.uuid4())[:8],
            task=task,
            steps=steps,
        )
        logger.info(f"Workflow {wf.workflow_id} created with {len(steps)} steps")
        return wf

    async def _plan_with_gemini(self, task: str) -> List[Dict]:
        """Use Gemini to dynamically generate workflow steps."""
        tools_desc = "\n".join(
            f"  - {name}: {info['description']} | params: {info['required_params']}"
            for name, info in config.AVAILABLE_TOOLS.items()
        )
        prompt = PLANNING_PROMPT.format(tools_description=tools_desc, task=task)

        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=2048,
            ),
        )

        raw = response.text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        steps = json.loads(raw)
        if not isinstance(steps, list) or len(steps) == 0:
            raise ValueError(f"Gemini returned invalid plan: {raw[:200]}")

        # Validate each step has required fields
        for i, step in enumerate(steps):
            if not all(k in step for k in ("tool", "action", "params")):
                raise ValueError(f"Step {i} missing required fields: {step}")
            tool_key = f"{step['tool']}.{step['action']}"
            if tool_key not in config.AVAILABLE_TOOLS:
                raise ValueError(f"Step {i} uses unknown tool: {tool_key}")

        logger.info(f"[Orchestrator] Gemini plan validated: {len(steps)} steps")
        for i, s in enumerate(steps):
            logger.info(f"  Step {i}: {s['tool']}.{s['action']}")
        return steps

    def _plan_with_templates(self, task: str) -> List[Dict]:
        """Rule-based fallback planner."""
        task_key = self._match_template(task)
        return FALLBACK_TEMPLATES[task_key]

    def _match_template(self, task: str) -> str:
        task_lower = task.lower()
        if any(kw in task_lower for kw in ("meeting", "schedule", "calendar", "sync")):
            return "schedule_meeting"
        return "schedule_meeting"
