import asyncio
import json
import logging
from datetime import datetime, timedelta

import config
from models.schemas import WorkflowState, WorkflowStatus, StepStatus
from agents.integration import IntegrationAgent
from agents.monitoring import MonitoringAgent
from agents.debug_agent import DebugAgent
from agents.fix_agent import FixAgent
from tools import calendar_tool
from db.database import save_workflow, add_log

logger = logging.getLogger("workflow.engine")

# ── Pretty log formatting ───────────────────────────────────────
B = "=" * 60
S = "-" * 50


def _log_banner(msg: str):
    logger.info("")
    logger.info(B)
    logger.info(f"  {msg}")
    logger.info(B)


def _log_section(msg: str):
    logger.info("")
    logger.info(S)
    logger.info(f"  {msg}")
    logger.info(S)


class WorkflowEngine:
    """
    Core self-healing loop:
        Execute -> Monitor -> Detect -> Diagnose -> Fix -> Validate -> Resume
    """

    def __init__(self):
        self.integration = IntegrationAgent()
        self.monitor = MonitoringAgent()
        self.debug_agent = DebugAgent()
        self.fix_agent = FixAgent()

    async def run(self, workflow: WorkflowState, simulate_failure: bool = True) -> WorkflowState:
        workflow.status = WorkflowStatus.RUNNING
        save_workflow(workflow)
        add_log(workflow.workflow_id, "INFO", f"Workflow started: {workflow.task}")

        _log_banner(f"WORKFLOW {workflow.workflow_id} STARTED")
        logger.info(f"  Task: {workflow.task}")
        logger.info(f"  Steps: {len(workflow.steps)}")
        logger.info(f"  Failure simulation: {simulate_failure}")
        logger.info(f"  Gemini: {'active' if config.GEMINI_API_KEY else 'fallback mode'}")

        if simulate_failure:
            calendar_tool.enable_failure_mode()
            add_log(workflow.workflow_id, "WARN", "Failure simulation ENABLED for calendar tool")

        for step in workflow.steps:
            _log_section(f"Step {step.id}: {step.tool}.{step.action}")

            # ── EXECUTE ──
            step = await self.integration.execute_step(step)
            save_workflow(workflow)

            # ── MONITOR ──
            if self.monitor.check_step(step):
                logger.info(f"  [OK] Step {step.id} completed successfully")
                add_log(workflow.workflow_id, "INFO",
                        f"Step {step.id} ({step.tool}.{step.action}) succeeded")

                # ── REASONING: adjust next create_event based on availability ──
                if step.tool == "calendar" and step.action == "list_meetings" and step.result:
                    self._adjust_next_event_slot(workflow, step)

                continue

            # ── FAILURE DETECTED ──
            logger.info("")
            logger.error(f"  [FAIL] Step {step.id}: {step.tool}.{step.action}")
            logger.error(f"  Error: {step.error}")
            logger.info("")
            logger.info(f"  >>> Entering Self-Healing Loop <<<")

            add_log(workflow.workflow_id, "ERROR", f"Step {step.id} failed: {step.error}")
            workflow.status = WorkflowStatus.HEALING
            save_workflow(workflow)

            await asyncio.sleep(1)

            healed = False
            for attempt in range(1, config.MAX_RETRIES + 1):
                logger.info("")
                logger.info(f"  ---- Healing Attempt {attempt}/{config.MAX_RETRIES} ----")
                add_log(workflow.workflow_id, "INFO", f"Healing attempt {attempt}")

                # ── PHASE 1: DIAGNOSE ──
                logger.info(f"  [Phase 1] DIAGNOSING root cause...")
                diagnosis = await self.debug_agent.diagnose(step)

                logger.info(f"")
                logger.info(f"  Debug Agent Analysis:")
                logger.info(f"    Root Cause    : {diagnosis.root_cause}")
                logger.info(f"    Fix Strategy  : {diagnosis.fix_strategy}")
                if diagnosis.field_mappings:
                    for old, new in diagnosis.field_mappings.items():
                        logger.info(f"    Field Mapping : '{old}' --> '{new}'")
                if diagnosis.format_conversions:
                    for field, conv in diagnosis.format_conversions.items():
                        logger.info(f"    Format Fix    : {field} -> {conv}")

                add_log(workflow.workflow_id, "INFO",
                        f"Diagnosis: {diagnosis.root_cause}")

                # ── PHASE 2: FIX ──
                logger.info(f"")
                logger.info(f"  [Phase 2] APPLYING fix...")
                fix_result = await self.fix_agent.fix(step, diagnosis)

                logger.info(f"")
                logger.info(f"  Fix Agent Result:")
                logger.info(f"    Description   : {fix_result.description}")
                logger.info(f"    Fixed Params  : {json.dumps(fix_result.fixed_params, indent=6)}")

                add_log(workflow.workflow_id, "INFO",
                        f"Fix applied: {fix_result.description}")

                # ── PHASE 3: RETRY ──
                step.params = fix_result.fixed_params
                calendar_tool.disable_failure_mode()

                logger.info(f"")
                logger.info(f"  [Phase 3] RETRYING with fixed params...")
                step.status = StepStatus.PENDING
                step = await self.integration.execute_step(step)
                save_workflow(workflow)

                # ── PHASE 4: VALIDATE ──
                if self.monitor.check_step(step):
                    step.status = StepStatus.HEALED
                    healed = True
                    healing_entry = {
                        "step_id": step.id,
                        "attempt": attempt,
                        "root_cause": diagnosis.root_cause,
                        "fix": fix_result.description,
                        "fixed_params": fix_result.fixed_params,
                        "outcome": "healed",
                    }
                    workflow.healing_log.append(healing_entry)

                    logger.info(f"")
                    logger.info(f"  [HEALED] Retry SUCCESSFUL!")
                    logger.info(f"  Step {step.id} healed on attempt {attempt}")
                    logger.info(f"  Workflow resuming...")

                    add_log(workflow.workflow_id, "INFO",
                            f"Step {step.id} HEALED on attempt {attempt}")
                    break
                else:
                    logger.warning(f"  [RETRY FAILED] Attempt {attempt} did not resolve the issue")
                    add_log(workflow.workflow_id, "WARN",
                            f"Healing attempt {attempt} failed, retrying...")
                    await asyncio.sleep(config.RETRY_DELAY_SEC)

            if not healed:
                workflow.status = WorkflowStatus.FAILED
                add_log(workflow.workflow_id, "ERROR",
                        f"Step {step.id} could not be healed after {config.MAX_RETRIES} attempts")
                save_workflow(workflow)
                logger.error(f"  WORKFLOW FAILED - step {step.id} unrecoverable")
                return workflow

        # ── ALL STEPS DONE ──
        # (reasoning helpers defined below)
        workflow.status = WorkflowStatus.COMPLETED
        save_workflow(workflow)
        add_log(workflow.workflow_id, "INFO", "Workflow COMPLETED successfully")

        _log_banner(f"WORKFLOW {workflow.workflow_id} COMPLETED")
        logger.info(f"  Status: {workflow.status.value}")
        for s in workflow.steps:
            icon = "[HEALED]" if s.status == StepStatus.HEALED else "[OK]"
            logger.info(f"    {icon} Step {s.id}: {s.tool}.{s.action} -> {s.status.value}")
        if workflow.healing_log:
            logger.info(f"  Self-healing was invoked {len(workflow.healing_log)} time(s)")

        return workflow

    # ── Multi-step reasoning helpers ───────────────────────────────

    def _adjust_next_event_slot(self, workflow: WorkflowState, list_step) -> None:
        """After list_meetings, find a free 1-hour slot and update the next create_event."""
        meetings = list_step.result.get("meetings", [])
        date = list_step.result.get("date", "2026-04-08")

        for next_step in workflow.steps:
            if (next_step.id > list_step.id
                    and next_step.tool == "calendar"
                    and next_step.action == "create_event"):
                free_slot = self._find_free_slot(meetings, date)
                if free_slot:
                    old_time = next_step.params.get("meeting_time", "unset")
                    next_step.params["meeting_time"] = free_slot
                    logger.info(f"")
                    logger.info(f"  [REASONING] Calendar availability checked:")
                    logger.info(f"    Busy slots : {len(meetings)}")
                    for m in meetings:
                        logger.info(f"      - {m['title']}: {m['start']} to {m['end']}")
                    logger.info(f"    Free slot  : {free_slot} (1 hour)")
                    logger.info(f"    Adjusted   : meeting_time {old_time} -> {free_slot}")
                    add_log(workflow.workflow_id, "INFO",
                            f"Reasoning: adjusted meeting to free slot {free_slot} "
                            f"(avoided {len(meetings)} conflicts)")
                else:
                    logger.warning(f"  [REASONING] No free 1-hour slot found on {date}")
                break

    @staticmethod
    def _find_free_slot(meetings: list, date: str) -> str | None:
        """Find the first available 1-hour slot between 9 AM and 5 PM."""
        busy = []
        for m in meetings:
            start = datetime.fromisoformat(m["start"])
            end = datetime.fromisoformat(m["end"])
            busy.append((start, end))

        base = datetime.fromisoformat(f"{date}T09:00:00")
        for hour_offset in range(8):  # 9 AM through 4 PM start
            slot_start = base + timedelta(hours=hour_offset)
            slot_end = slot_start + timedelta(hours=1)
            conflict = any(s < slot_end and e > slot_start for s, e in busy)
            if not conflict:
                return slot_start.isoformat()
        return None
