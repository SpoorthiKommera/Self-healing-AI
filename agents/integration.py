import logging

from tools import calendar_tool, slack_tool, notes_tool
from models.schemas import WorkflowStep, StepStatus

logger = logging.getLogger("agents.integration")

# Dispatch table: (tool, action) → callable
TOOL_REGISTRY = {
    ("calendar", "list_meetings"): calendar_tool.list_meetings,
    ("calendar", "create_event"): calendar_tool.create_event,
    ("slack", "send_message"): slack_tool.send_message,
    ("notes", "create_note"): notes_tool.create_note,
}


class IntegrationAgent:
    """Executes a single workflow step by calling the appropriate mock tool."""

    async def execute_step(self, step: WorkflowStep) -> WorkflowStep:
        key = (step.tool, step.action)
        handler = TOOL_REGISTRY.get(key)
        if not handler:
            step.status = StepStatus.FAILED
            step.error = f"Unknown tool/action: {key}"
            return step

        step.status = StepStatus.RUNNING
        step.attempt += 1
        logger.info(
            f"[Step {step.id}] Executing {step.tool}.{step.action} "
            f"(attempt {step.attempt}) params={step.params}"
        )

        # If calendar failure mode is on, corrupt params BEFORE calling the tool
        if step.tool == "calendar" and calendar_tool.is_failure_mode():
            logger.warning("[Step %d] Failure mode ON — transforming to broken schema", step.id)
            step.params = calendar_tool.transform_to_broken_schema(step.params)

        try:
            result = await handler(step.params)
            step.status = StepStatus.SUCCESS
            step.result = result
            logger.info(f"[Step {step.id}] ✓ Success")
        except Exception as exc:
            step.status = StepStatus.FAILED
            step.error = str(exc)
            logger.error(f"[Step {step.id}] ✗ Failed: {exc}")

        return step
