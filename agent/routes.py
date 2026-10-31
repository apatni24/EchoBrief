"""Agent HTTP routes mounted on the resolver app."""

from __future__ import annotations

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import JSONResponse

from agent import cache_gate, jobs
from agent.audit import read as read_audit
from agent.catalog import build_capabilities, openapi_extras
from agent.errors import HTTP_STATUS, AgentError, error_dict
from agent.schemas import ApprovalDecisionInput
from agent.summarize import resume_job, start_summarize
from agent import approvals
from redis_stream_client import SUMMARIZATION_GROUP, TRANSCRIPTION_GROUP, group_exists, redis_client

router = APIRouter()


def _error_response(exc: AgentError, job_id: str | None = None) -> JSONResponse:
    body = exc.as_body()
    if job_id:
        body["job_id"] = job_id
    return JSONResponse(status_code=exc.status_code, content=body)


def _action_status(job: dict) -> int:
    state = job.get("status")
    error_code = (job.get("error") or {}).get("code")
    if state == "done":
        return 200
    if state == "failed":
        return HTTP_STATUS.get(error_code, 500)
    if state == "expired":
        return HTTP_STATUS.get(error_code, 409)
    if state not in jobs.TERMINAL and error_code == "rate_limited":
        return 429
    return 202


def _poll_status(job: dict) -> int:
    state = job.get("status")
    error_code = (job.get("error") or {}).get("code")
    if state == "failed" and error_code == "timeout":
        return 504
    if state == "expired":
        return 409
    if state not in jobs.TERMINAL and error_code == "rate_limited":
        return 429
    return 200


def _from_start(result) -> JSONResponse:
    job = result.job
    if result.kind == "failed":
        error = (job or {}).get("error") or error_dict("internal")
        status = HTTP_STATUS.get(error.get("code"), 500)
        body = {"error": error}
        if job:
            body["job_id"] = job["job_id"]
        return JSONResponse(status_code=status, content=body)
    if not job:
        return _error_response(AgentError("internal"))
    return JSONResponse(status_code=_action_status(job), content=jobs.public_view(job))


@router.get(
    "/.well-known/echobrief/capabilities.json",
    operation_id="get_capabilities",
    tags=["agent"],
)
def capabilities():
    return build_capabilities()


@router.get("/health", operation_id="get_health", tags=["agent"], openapi_extra=openapi_extras("get_health"))
def health():
    redis_status = "ok"
    try:
        if not redis_client.ping():
            redis_status = "unavailable"
    except Exception:
        redis_status = "unavailable"
    body = {
        "status": "ok" if redis_status == "ok" else "degraded",
        "redis": redis_status,
        "consumer_groups": {
            "transcription": group_exists("audio_uploaded", TRANSCRIPTION_GROUP),
            "summarization": group_exists("transcription_complete", SUMMARIZATION_GROUP),
        },
    }
    return body


@router.post(
    "/agent/v1/episodes/summaries",
    operation_id="summarize_episode",
    tags=["agent"],
    openapi_extra=openapi_extras("summarize_episode"),
)
def summarize_episode(
    payload: dict = Body(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not isinstance(payload, dict):
        return _error_response(AgentError("invalid_input", retryable=False))
    try:
        result = start_summarize(
            payload.get("url") or "",
            payload.get("summary_type") or "",
            idempotency_key=idempotency_key,
        )
    except AgentError as exc:
        return _error_response(exc)
    except Exception:
        return _error_response(AgentError("internal", retryable=True))
    return _from_start(result)


@router.get(
    "/agent/v1/jobs/{job_id}",
    operation_id="get_job",
    tags=["agent"],
    openapi_extra=openapi_extras("get_job"),
)
def get_job(job_id: str):
    jobs.sweep_deadlines()
    job = jobs.expire_if_needed(jobs.get_job(job_id))
    if not job:
        return _error_response(AgentError("not_found", "Unknown job_id.", retryable=False))
    return JSONResponse(status_code=_poll_status(job), content=jobs.public_view(job))


@router.get(
    "/agent/v1/jobs/{job_id}/audit",
    operation_id="get_job_audit",
    tags=["agent"],
    openapi_extra=openapi_extras("get_job_audit"),
)
def get_job_audit(job_id: str):
    job = jobs.get_job(job_id)
    if not job:
        return _error_response(AgentError("not_found", "Unknown job_id.", retryable=False))
    return {"job_id": job_id, "audit": read_audit(job_id)}


@router.post(
    "/agent/v1/jobs/{job_id}/retry",
    operation_id="retry_job",
    tags=["agent"],
    openapi_extra=openapi_extras("retry_job"),
)
def retry_job(job_id: str):
    existing = jobs.get_job(job_id)
    if not existing:
        return _error_response(AgentError("not_found", "Unknown job_id.", retryable=False))
    if existing.get("status") != "failed":
        return JSONResponse(status_code=_poll_status(existing), content=jobs.public_view(existing))
    try:
        resumed = resume_job(job_id)
    except AgentError as exc:
        return _error_response(exc, job_id)
    except Exception:
        return _error_response(AgentError("internal", retryable=True), job_id)
    if resumed is None:
        return _error_response(
            AgentError("invalid_input", "This job cannot be resumed.", retryable=False),
            job_id,
        )
    return _from_start(resumed)


@router.get(
    "/agent/v1/summaries",
    operation_id="get_summary",
    tags=["agent"],
    openapi_extra=openapi_extras("get_summary"),
)
def get_summary(
    platform: str = Query(...),
    episode_id: str = Query(...),
    summary_type: str = Query(...),
):
    if summary_type not in ("bs", "ns", "ts") or platform not in ("apple", "spotify") or not episode_id:
        return _error_response(AgentError("invalid_input", retryable=False))
    from cache_service import CacheService
    cached_episode = CacheService.get_cached_episode(platform, episode_id, summary_type)
    if not cached_episode:
        return _error_response(AgentError("not_found", "No cached summary for that episode.", retryable=False))
    return {
        "summary": cached_episode.get("summary"),
        "metadata": cached_episode.get("metadata"),
        "cached": True,
        "cached_at": cached_episode.get("cached_at"),
        "platform": platform,
        "episode_id": episode_id,
        "summary_type": summary_type,
    }


@router.post(
    "/agent/v1/approvals/{approval_id}/decision",
    operation_id="decide_approval",
    tags=["human"],
    openapi_extra=openapi_extras("decide_approval"),
)
def decide_approval(approval_id: str, payload: ApprovalDecisionInput):
    try:
        job = approvals.decide(approval_id, payload.decision)
    except AgentError as exc:
        return _error_response(exc)
    except Exception:
        return _error_response(AgentError("internal", retryable=True))
    return JSONResponse(status_code=200, content=jobs.public_view(job))


@router.post(
    "/agent/v1/cache/clear",
    operation_id="clear_cache",
    tags=["agent"],
    openapi_extra=openapi_extras("clear_cache"),
)
def clear_cache_request():
    body = cache_gate.request_clear()
    return JSONResponse(status_code=202, content=body)
