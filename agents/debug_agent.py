import asyncio
import json
import logging
from typing import Dict

from google import genai
from google.genai import types

import config
from models.schemas import DiagnosisResult, WorkflowStep

logger = logging.getLogger("agents.debug")

DIAGNOSIS_PROMPT = """\
You are a distributed systems debugger specializing in API integration failures.

A workflow step failed. Analyze the error and determine the root cause.

**Tool:** {tool}.{action}
**Parameters sent:** {params}
**Error message:** {error}

The target API schema expects:
{expected_schema}

COMMON FAILURE PATTERNS:
1. Schema mismatch: field renamed (e.g. "meeting_time" -> "time")
2. Format change: ISO 8601 -> human-readable ("10:00 AM")
3. Missing required fields after upstream API changes
4. Type mismatch: string vs list, int vs string

Analyze and respond with ONLY a JSON object (no markdown fences, no explanation):
{{
  "root_cause": "<precise one-line explanation of what went wrong>",
  "fix_strategy": "<specific action to fix it>",
  "field_mappings": {{"<received_field>": "<expected_field>"}},
  "format_conversions": {{"<field>": "<conversion description>"}}
}}

If no field mapping is needed, use empty dict {{}}.
If no format conversion is needed, use empty dict {{}}.
"""


class DebugAgent:
    """Uses Gemini to diagnose the root cause of a step failure.
    Falls back to rule-based diagnosis when Gemini is unavailable."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if not config.GEMINI_API_KEY:
                raise RuntimeError("GEMINI_API_KEY not set")
            self._client = genai.Client(api_key=config.GEMINI_API_KEY)
        return self._client

    async def diagnose(self, step: WorkflowStep) -> DiagnosisResult:
        logger.info(f"[DebugAgent] Diagnosing step {step.id}: {step.error}")

        try:
            result = await self._gemini_diagnose(step)
            logger.info(f"[DebugAgent] Gemini diagnosis: {result.root_cause}")
            return result
        except Exception as exc:
            logger.warning(f"[DebugAgent] Gemini unavailable ({exc}), using rule-based fallback")
            return self._fallback_diagnosis(step)

    async def _gemini_diagnose(self, step: WorkflowStep) -> DiagnosisResult:
        # Build expected schema description from config
        tool_key = f"{step.tool}.{step.action}"
        tool_info = config.AVAILABLE_TOOLS.get(tool_key, {})
        expected = json.dumps(tool_info, indent=2) if tool_info else "Unknown tool schema"

        prompt = DIAGNOSIS_PROMPT.format(
            tool=step.tool,
            action=step.action,
            params=json.dumps(step.params, indent=2),
            error=step.error,
            expected_schema=expected,
        )

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
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        data = json.loads(raw)
        return DiagnosisResult(**data)

    def _fallback_diagnosis(self, step: WorkflowStep) -> DiagnosisResult:
        """Deterministic rule-based diagnosis when Gemini is unavailable."""
        params = step.params
        error = step.error or ""

        # Detect schema mismatch patterns
        field_mappings: Dict[str, str] = {}
        format_conversions: Dict[str, str] = {}
        root_cause = "Unknown failure"
        fix_strategy = "Retry with corrected parameters"

        # Pattern 1: Field renamed (e.g. "time" present but "meeting_time" missing)
        if "time" in params and "meeting_time" not in params:
            field_mappings["time"] = "meeting_time"
            root_cause = "Schema mismatch: field 'meeting_time' was renamed to 'time' by upstream"
            fix_strategy = "Rename 'time' back to 'meeting_time' and convert to ISO 8601 format"

        # Pattern 2: Format changed but field name is correct
        if "meeting_time" in params:
            try:
                from datetime import datetime
                datetime.fromisoformat(params["meeting_time"])
            except (ValueError, TypeError):
                format_conversions["meeting_time"] = "Convert to ISO 8601 datetime"
                root_cause = "Format mismatch: 'meeting_time' is not in ISO 8601 format"
                fix_strategy = "Parse and convert meeting_time to ISO 8601"

        # Pattern 3: If field was mapped, also check format
        if "time" in field_mappings:
            format_conversions["meeting_time"] = "Convert human-readable date/time string to ISO 8601 datetime"

        # Pattern 4: Missing required fields entirely
        if "missing fields" in error.lower():
            for field in ["title", "participants", "meeting_time"]:
                if field in error and field not in params:
                    if field not in field_mappings.values():
                        field_mappings[field] = field  # Signal to restore from template

        if not field_mappings and not format_conversions:
            root_cause = f"Step failed with error: {error[:100]}"
            fix_strategy = "Retry with original parameters"

        result = DiagnosisResult(
            root_cause=root_cause,
            fix_strategy=fix_strategy,
            field_mappings=field_mappings,
            format_conversions=format_conversions,
        )
        logger.info(f"[DebugAgent] Fallback diagnosis: {result.root_cause}")
        return result
