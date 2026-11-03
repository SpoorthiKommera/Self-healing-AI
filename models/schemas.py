from enum import Enum
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    HEALED = "healed"


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    HEALING = "healing"


class TaskRequest(BaseModel):
    task: str
    simulate_failure: bool = True


class WorkflowStep(BaseModel):
    id: int = 0
    tool: str
    action: str
    params: Dict
    status: StepStatus = StepStatus.PENDING
    result: Optional[Dict] = None
    error: Optional[str] = None
    attempt: int = 0


class WorkflowState(BaseModel):
    workflow_id: str
    task: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    steps: List[WorkflowStep] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    healing_log: List[Dict] = []


class DiagnosisResult(BaseModel):
    root_cause: str
    fix_strategy: str
    field_mappings: Dict = {}
    format_conversions: Dict = {}


class FixResult(BaseModel):
    fixed_params: Dict
    description: str
    success: bool
