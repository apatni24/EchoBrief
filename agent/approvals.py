"""Single-use approval records. The decision route is not an agent tool."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from agent import jobs
from agent.errors import AgentError
from redis_stream_client import redis_client

_RUNNERS: dict = {}
# Keep the record past the decision window so a late call returns approval_expired.
RECORD_GRACE_SECONDS = 24 * 60 * 60


def register_runner(operation: str, fn) -> None:
    _RUNNERS[operation] = fn


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _key(approval_id: str) -> str:
    return f"approval:{approval_id}"


def _pending_index(operation: str, digest: str) -> str:
    return f"approval-pending:{operation}:{digest}"


def _save(approval: dict, ttl: int) -> None:
    redis_client.setex(_key(approval["id"]), ttl, json.dumps(approval))


def get_approval(approval_id: str) -> dict | None:
    raw = redis_client.get(_key(approval_id))
    if not raw:
        return None
    return json.loads(raw)


def is_expired(approval: dict) -> bool:
    expires_at = approval.get("expires_at")
    if not expires_at:
        return False
    return _now() > datetime.fromisoformat(expires_at)


def create_approval(operation: str, args: dict, job_id: str, expires_in_seconds: int) -> dict:
    digest = jobs.args_hash(args)
    existing_id = redis_client.get(_pending_index(operation, digest))
    if existing_id:
        existing = get_approval(existing_id)
        if existing and existing.get("status") == "pending" and not is_expired(existing):
            return existing
    approval_id = str(uuid.uuid4())
    expires_at = (_now() + timedelta(seconds=expires_in_seconds)).isoformat()
    if expires_in_seconds <= 0:
        expires_at = (_now() - timedelta(seconds=1)).isoformat()
    approval = {
        "id": approval_id,
        "operation": operation,
        "args_hash": digest,
        "args": args,
        "status": "pending",
        "job_id": job_id,
        "expires_at": expires_at,
        "created_at": jobs.now_iso(),
    }
    ttl = RECORD_GRACE_SECONDS if expires_in_seconds <= 0 else expires_in_seconds + RECORD_GRACE_SECONDS
    _save(approval, ttl)
    redis_client.set(_pending_index(operation, digest), approval_id, ex=ttl)
    return approval


def _mark(approval: dict, status: str) -> None:
    approval["status"] = status
    raw_ttl = RECORD_GRACE_SECONDS
    _save(approval, raw_ttl)
    redis_client.delete(_pending_index(approval["operation"], approval["args_hash"]))
    job = jobs.get_job(approval["job_id"])
    if job and job.get("approval"):
        job["approval"]["status"] = status
        job["updated_at"] = jobs.now_iso()
        jobs.save_job(job)


def decide(approval_id: str, decision: str) -> dict:
    if decision not in ("approve", "deny"):
        raise AgentError("invalid_input", "decision must be approve or deny.", retryable=False)
    approval = get_approval(approval_id)
    if not approval:
        raise AgentError("not_found", "Unknown approval id.", retryable=False)
    job = jobs.get_job(approval["job_id"])
    if is_expired(approval):
        _mark(approval, "expired")
        if job and job["status"] not in jobs.TERMINAL:
            from agent.errors import error_dict
            jobs.transition(
                job["job_id"],
                "expired",
                error=error_dict("approval_expired", retryable=False),
            )
        raise AgentError("approval_expired", retryable=False)
    if approval["status"] != "pending":
        current = jobs.get_job(approval["job_id"])
        if not current:
            raise AgentError("not_found", retryable=False)
        return current
    lock_key = f"approval-run:{approval_id}"
    if not redis_client.set(lock_key, "1", nx=True, ex=RECORD_GRACE_SECONDS):
        current = jobs.get_job(approval["job_id"])
        if current:
            return current
        raise AgentError("not_found", retryable=False)
    if decision == "deny":
        _mark(approval, "denied")
        if job and job["status"] not in jobs.TERMINAL:
            jobs.transition(job["job_id"], "cancelled", error=None)
        current = jobs.get_job(approval["job_id"])
        return current or job
    _mark(approval, "approved")
    runner = _RUNNERS.get(approval["operation"])
    if runner is None:
        if job:
            jobs.fail_job(job["job_id"], "internal", "No runner is registered for this operation.", retryable=False)
        raise AgentError("internal", "No runner is registered for this operation.", retryable=False)
    try:
        runner(approval.get("args") or {}, approval["job_id"])
    except AgentError:
        raise
    except Exception:
        current = jobs.get_job(approval["job_id"])
        if current and current["status"] not in jobs.TERMINAL:
            jobs.fail_job(approval["job_id"], "internal", retryable=True)
        raise AgentError("internal", retryable=True)
    current = jobs.get_job(approval["job_id"])
    if not current:
        raise AgentError("not_found", retryable=False)
    return current
