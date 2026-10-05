from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StepOutput(BaseModel):
    stage: str
    status: Literal["pending", "running", "succeeded", "failed", "skipped", "canceled"]
    reason: str | None


class SafeError(BaseModel):
    code: str
    message: str
    request_id: UUID
    details: dict


class HistoricalStep(StepOutput):
    artifact: dict | None
    completed_attempt: int | None


class AttemptOutput(BaseModel):
    attempt: int = Field(ge=1)
    status: Literal["failed"]
    error: SafeError | None
    steps: list[HistoricalStep]


class JobOutput(BaseModel):
    id: UUID
    revision: int = Field(ge=1)
    status: Literal["queued", "running", "succeeded", "failed", "cancel_requested", "canceled"]
    current_stage: str | None
    attempt: int = Field(ge=1)
    progress: float | None = Field(ge=0, le=1)
    steps: list[StepOutput]
    error: SafeError | None
    attempt_history: list[AttemptOutput]
    can_retry: bool
    cancel_requested: bool


class CancelInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(gt=0, strict=True)


class RetryInput(CancelInput):
    from_stage: str = Field(min_length=1, max_length=80)
