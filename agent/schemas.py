"""Pydantic models for the agent HTTP surface."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SummarizeInput(BaseModel):
    url: str
    summary_type: str = Field(description="bs bullet points, ns narrative, or ts takeaways")


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool
    retry_after_seconds: int | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class ApprovalDecisionInput(BaseModel):
    decision: str = Field(description="approve or deny")


class JobView(BaseModel):
    job_id: str
    operation: str
    status: str
    input: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: ErrorBody | None = None
    approval: dict[str, Any] | None = None
    poll_url: str | None = None
    cached: bool | None = None
