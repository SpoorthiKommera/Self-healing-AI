import logging
from typing import Dict, List

from models.schemas import WorkflowState, WorkflowStep, StepStatus

logger = logging.getLogger("agents.monitoring")


class MonitoringAgent:
    """Observes workflow execution and detects failures."""

    def check_step(self, step: WorkflowStep) -> bool:
        """Returns True if step is healthy, False if failed."""
        if step.status == StepStatus.FAILED:
            error_msg = step.error or "Unknown error"

            # Detect specific failure patterns for clear logging
            if "missing fields" in error_msg.lower() or "schema" in error_msg.lower():
                logger.error(
                    f"[Monitor] SCHEMA MISMATCH DETECTED on step {step.id} "
                    f"({step.tool}.{step.action}): {error_msg}"
                )
            else:
                logger.error(
                    f"[Monitor] FAILURE DETECTED on step {step.id} "
                    f"({step.tool}.{step.action}): {error_msg}"
                )
            return False

        logger.info(f"[Monitor] Step {step.id} ({step.tool}.{step.action}): HEALTHY")
        return True

    def workflow_health(self, workflow: WorkflowState) -> Dict:
        failed = [s for s in workflow.steps if s.status == StepStatus.FAILED]
        succeeded = [s for s in workflow.steps if s.status == StepStatus.SUCCESS]
        return {
            "workflow_id": workflow.workflow_id,
            "total_steps": len(workflow.steps),
            "succeeded": len(succeeded),
            "failed": len(failed),
            "failed_steps": [
                {"step_id": s.id, "tool": s.tool, "action": s.action, "error": s.error}
                for s in failed
            ],
        }
