import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import Column, Integer, String, Text, DateTime, create_engine
from sqlalchemy.orm import Session, declarative_base

import config

logger = logging.getLogger("db")

Base = declarative_base()


class WorkflowRecord(Base):
    __tablename__ = "workflows"
    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(String(32), unique=True, index=True)
    task = Column(String(256))
    status = Column(String(32))
    steps_json = Column(Text)
    healing_log_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LogRecord(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(String(32), index=True)
    level = Column(String(16))
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


# Synchronous SQLite engine (simple, hackathon-friendly)
# Strip aiosqlite driver if present; use /tmp so Cloud Run doesn't crash
_db_url = config.DATABASE_URL.replace("+aiosqlite", "")
engine = create_engine(_db_url, echo=False)
Base.metadata.create_all(engine)
logger.info(f"Database initialized: {_db_url}")


def save_workflow(workflow_state) -> None:
    with Session(engine) as session:
        existing = (
            session.query(WorkflowRecord)
            .filter_by(workflow_id=workflow_state.workflow_id)
            .first()
        )
        steps_data = [s.model_dump(mode="json") for s in workflow_state.steps]
        if existing:
            existing.status = workflow_state.status.value
            existing.steps_json = json.dumps(steps_data)
            existing.healing_log_json = json.dumps(workflow_state.healing_log)
            existing.updated_at = datetime.utcnow()
        else:
            record = WorkflowRecord(
                workflow_id=workflow_state.workflow_id,
                task=workflow_state.task,
                status=workflow_state.status.value,
                steps_json=json.dumps(steps_data),
                healing_log_json=json.dumps(workflow_state.healing_log),
            )
            session.add(record)
        session.commit()
    logger.debug(f"Workflow {workflow_state.workflow_id} saved")


def get_workflow(workflow_id: str) -> Optional[Dict]:
    with Session(engine) as session:
        record = (
            session.query(WorkflowRecord)
            .filter_by(workflow_id=workflow_id)
            .first()
        )
        if not record:
            return None
        return {
            "workflow_id": record.workflow_id,
            "task": record.task,
            "status": record.status,
            "steps": json.loads(record.steps_json),
            "healing_log": json.loads(record.healing_log_json),
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }


def add_log(workflow_id: str, level: str, message: str) -> None:
    with Session(engine) as session:
        session.add(LogRecord(workflow_id=workflow_id, level=level, message=message))
        session.commit()


def get_logs(workflow_id: str) -> List[Dict]:
    with Session(engine) as session:
        rows = (
            session.query(LogRecord)
            .filter_by(workflow_id=workflow_id)
            .order_by(LogRecord.created_at)
            .all()
        )
        return [
            {"level": r.level, "message": r.message, "ts": r.created_at.isoformat()}
            for r in rows
        ]
