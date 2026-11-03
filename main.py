import logging
import os
import sys
from datetime import datetime

from fastapi import FastAPI, HTTPException

import config
from models.schemas import TaskRequest
from agents.orchestrator import OrchestratorAgent
from workflow.engine import WorkflowEngine
from db.database import get_workflow, get_logs

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(name)-24s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger("main")

app = FastAPI(
    title="Self-Healing Multi-Agent Productivity Assistant",
    version="3.0.0",
    description="Hackathon-standard system using Google ADK, MCP Toolbox, and AlloyDB-ready architecture",
)
orchestrator = OrchestratorAgent()
engine = WorkflowEngine()


@app.on_event("startup")
async def startup():
    logger.info("=" * 60)
    logger.info("  Self-Healing Multi-Agent Assistant v3.0 (ADK + MCP)")
    logger.info(f"  PORT      = {config.PORT}")
    logger.info(f"  GEMINI    = {'active (' + config.GEMINI_MODEL + ')' if config.GEMINI_API_KEY else 'fallback mode (no API key)'}")
    logger.info(f"  SLACK     = {'real webhook' if config.SLACK_WEBHOOK_URL else 'mock mode'}")
    logger.info(f"  DB        = {config.DATABASE_URL}")
    logger.info("=" * 60)


@app.post("/execute-task")
async def execute_task(req: TaskRequest):
    """
    Accept a natural-language task, execute via ADK LlmAgent with MCP tools.
    """
    logger.info(f"Received task: '{req.task}' (simulate_failure={req.simulate_failure})")
    workflow = await orchestrator.parse_task(req.task, req.simulate_failure)
    result = await engine.run(workflow, req.simulate_failure)
    return result.model_dump(mode="json")


@app.get("/workflow-status/{workflow_id}")
async def workflow_status(workflow_id: str):
    """Retrieve persisted workflow state + logs."""
    record = get_workflow(workflow_id)
    if not record:
        raise HTTPException(status_code=404, detail="Workflow not found")
    record["logs"] = get_logs(workflow_id)
    return record


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "3.0.0",
        "gemini": "active" if config.GEMINI_API_KEY else "fallback",
        "slack": "webhook" if config.SLACK_WEBHOOK_URL else "mock",
        "port": config.PORT,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, reload=True)
