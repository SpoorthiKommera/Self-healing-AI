import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List

from google import genai
from google.genai import types

import config
from models.schemas import DiagnosisResult, FixResult, WorkflowStep

logger = logging.getLogger("agents.fix")

FIX_PROMPT = """\
You are a self-healing agent that fixes broken API parameters.

A workflow step failed and has been diagnosed. Apply the fix.

**Failed step:** {tool}.{action}
**Current params (broken):** {params}

**Diagnosis:**
- Root cause: {root_cause}
- Fix strategy: {fix_strategy}
- Field mappings needed: {field_mappings}
- Format conversions needed: {format_conversions}

**Target API schema:**
{expected_schema}

INSTRUCTIONS:
1. Rename fields according to field_mappings
2. Convert formats according to format_conversions
3. Ensure all required fields are present with valid values
4. meeting_time MUST be ISO 8601 format: "YYYY-MM-DDTHH:MM:SS"
5. If a value like "10:00 AM" needs to become ISO 8601, use date 2026-04-05

Return ONLY a JSON object (no markdown, no explanation):
{{
  "fixed_params": {{...the corrected parameters...}},
  "description": "<brief summary of what was changed>"
}}
"""


class FixAgent:
    """Uses Gemini to produce corrected parameters, with a deterministic fallback."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if not config.GEMINI_API_KEY:
                raise RuntimeError("GEMINI_API_KEY not set")
            self._client = genai.Client(api_key=config.GEMINI_API_KEY)
        return self._client

    async def fix(self, step: WorkflowStep, diagnosis: DiagnosisResult) -> FixResult:
        logger.info(f"[FixAgent] Attempting to fix step {step.id}")

        try:
            result = await self._gemini_fix(step, diagnosis)
            logger.info(f"[FixAgent] Gemini fix applied: {result.description}")
            return result
        except Exception as exc:
            logger.warning(f"[FixAgent] Gemini unavailable ({exc}), using deterministic fallback")
            return self._fallback_fix(step, diagnosis)

    async def _gemini_fix(self, step: WorkflowStep, diagnosis: DiagnosisResult) -> FixResult:
        tool_key = f"{step.tool}.{step.action}"
        tool_info = config.AVAILABLE_TOOLS.get(tool_key, {})

        prompt = FIX_PROMPT.format(
            tool=step.tool,
            action=step.action,
            params=json.dumps(step.params, indent=2),
            root_cause=diagnosis.root_cause,
            fix_strategy=diagnosis.fix_strategy,
            field_mappings=json.dumps(diagnosis.field_mappings),
            format_conversions=json.dumps(diagnosis.format_conversions),
            expected_schema=json.dumps(tool_info, indent=2),
        )

        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
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
        result = FixResult(
            fixed_params=data["fixed_params"],
            description=data.get("description", "Gemini-applied fix"),
            success=True,
        )
        logger.info(f"[FixAgent] Fixed params: {json.dumps(result.fixed_params)}")
        return result

    def _fallback_fix(self, step: WorkflowStep, diagnosis: DiagnosisResult) -> FixResult:
        """Deterministic rule-based fix."""
        fixed = dict(step.params)
        changes: List[str] = []

        # 1. Apply field mappings (rename fields)
        for old_field, new_field in diagnosis.field_mappings.items():
            if old_field in fixed and new_field not in fixed:
                fixed[new_field] = fixed.pop(old_field)
                changes.append(f"Mapped '{old_field}' -> '{new_field}'")

        # 2. Apply format conversions
        for field, conversion in diagnosis.format_conversions.items():
            if field in fixed:
                val = fixed[field]
                if "ISO" in conversion or "iso" in conversion or "8601" in conversion:
                    converted = self._to_iso(val)
                    if converted != val:
                        fixed[field] = converted
                        changes.append(f"Converted '{field}': '{val}' -> '{converted}'")

        # 3. Restore missing required fields from template
        from agents.orchestrator import TASK_TEMPLATES
        template_steps = TASK_TEMPLATES.get("schedule_meeting", [])
        template_params = template_steps[0].get("params", {}) if template_steps else {}
        for required in ["meeting_time", "title", "participants"]:
            if required not in fixed and required in template_params:
                fixed[required] = template_params[required]
                changes.append(f"Restored missing '{required}' from template")

        desc = "; ".join(changes) if changes else "No changes applied"
        logger.info(f"[FixAgent] Fallback fix: {desc}")
        return FixResult(fixed_params=fixed, description=desc, success=True)

    @staticmethod
    def _to_iso(value: str) -> str:
        """Best-effort parse of time string -> ISO 8601."""
        for fmt in (
            "%b %d at %I:%M %p",   # "Apr 08 at 11:00 AM" (date-aware broken format)
            "%I:%M %p",
            "%I:%M%p",
            "%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                dt = datetime.strptime(value.strip(), fmt)
                if dt.year == 1900:
                    # Keep parsed month/day if available, only fill year
                    dt = dt.replace(year=2026)
                return dt.isoformat()
            except ValueError:
                continue
        return value
