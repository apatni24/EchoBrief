"""Durable summarize workflow stored at job:{job_id}."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from agent import audit
from agent.errors import error_dict
from redis_stream_client import redis_client

JOB_TTL_SECONDS = 7 * 24 * 60 * 60
IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60
DEADLINE_SECONDS = 240
ATTEMPT_LIMIT = 3
ACTIVE_KEY = "jobs:active"

TERMINAL = frozenset({"done", "failed", "cancelled", "expired"})
ALLOWED = {
    "accepted": {"resolving", "failed", "cancelled", "expired"},
    "awaiting_approval": {"resolving", "done", "cancelled", "expired", "failed"},
    "resolving": {"transcribing", "failed", "cancelled", "expired"},
    "transcribing": {"summarizing", "failed", "cancelled", "expired"},
    "summarizing": {"done", "failed", "cancelled", "expired"},
}

PUBLIC_HIDDEN = {"artifacts", "file_hash", "transcript_hash"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def is_past(value: str | None) -> bool:
    if not value:
        return False
    return datetime.now(timezone.utc) > parse_iso(value)


def is_terminal(job: dict | None) -> bool:
    return bool(job) and job.get("status") in TERMINAL


def body_hash(url: str, summary_type: str) -> str:
    payload = json.dumps({"url": url.strip(), "summary_type": summary_type}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def args_hash(args: dict) -> str:
    payload = json.dumps(args, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _key(job_id: str) -> str:
    return f"job:{job_id}"


def _inflight_key(platform: str, episode_id: str, summary_type: str) -> str:
    return f"inflight:{platform}:{episode_id}:{summary_type}"


def _idempotency_key(operation: str, key: str) -> str:
    return f"idempotency:{operation}:{key}"


def _save(job: dict) -> None:
    redis_client.setex(_key(job["job_id"]), JOB_TTL_SECONDS, json.dumps(job))


def save_job(job: dict) -> None:
    _save(job)


def get_job(job_id: str) -> dict | None:
    raw = redis_client.get(_key(job_id))
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode()
    return json.loads(raw)


def public_view(job: dict, *, include_poll: bool = True) -> dict:
    view = {key: value for key, value in job.items() if key not in PUBLIC_HIDDEN}
    if include_poll:
        view["poll_url"] = f"/agent/v1/jobs/{job['job_id']}"
    result = job.get("result") or {}
    view["cached"] = bool(result.get("cached")) if result else False
    approval = job.get("approval") or {}
    if approval.get("id"):
        view["approval_id"] = approval["id"]
    return view


def create_job(*, operation: str, status: str, input_data: dict, platform: str | None = None,
               episode_id: str | None = None, idempotency_key: str | None = None,
               with_deadline: bool = True, approval: dict | None = None,
               result: dict | None = None, error: dict | None = None) -> dict:
    job_id = str(uuid.uuid4())
    created = now_iso()
    deadline_at = None
    if with_deadline and status not in TERMINAL and status != "awaiting_approval":
        deadline_at = (datetime.now(timezone.utc) + timedelta(seconds=DEADLINE_SECONDS)).isoformat()
    job = {
        "job_id": job_id,
        "operation": operation,
        "idempotency_key": idempotency_key,
        "input": input_data,
        "platform": platform,
        "episode_id": episode_id,
        "status": status,
        "stage_timestamps": {status: created},
        "attempts": {"resolving": 0, "transcribing": 0, "summarizing": 0},
        "result": result,
        "error": error,
        "approval": approval,
        "deadline_at": deadline_at,
        "created_at": created,
        "updated_at": created,
        "transcript_length": None,
        "transcript_hash": None,
        "file_hash": None,
        "cache_flags": {"episode": False, "transcript": False, "file": False},
        "artifacts": {"file_path": None, "metadata": None},
    }
    _save(job)
    if status not in TERMINAL:
        redis_client.sadd(ACTIVE_KEY, job_id)
    audit.append(job_id, status, "created")
    return job


def transition(job_id: str, new_status: str, **updates) -> dict | None:
    job = get_job(job_id)
    if not job:
        return None
    current = job["status"]
    if current in TERMINAL:
        return None
    if new_status != current and new_status not in ALLOWED.get(current, set()):
        return None
    changed = new_status != current or bool(updates)
    if not changed:
        return job
    stamp = now_iso()
    job["status"] = new_status
    job["updated_at"] = stamp
    job["stage_timestamps"][new_status] = stamp
    for key, value in updates.items():
        job[key] = value
    if new_status in TERMINAL:
        release_inflight(job)
        redis_client.srem(ACTIVE_KEY, job_id)
    else:
        redis_client.sadd(ACTIVE_KEY, job_id)
    _sync_resume_index(job)
    _save(job)
    audit.append(job_id, new_status, "transition", error_code=(job.get("error") or {}).get("code"))
    if new_status == "done":
        from agent.webhook import notify_completed
        notify_completed(job)
    return job


def fail_job(job_id: str, code: str, message: str | None = None, *, retryable: bool | None = None,
             retry_after_seconds: int | None = None) -> dict | None:
    return transition(
        job_id,
        "failed",
        error=error_dict(code, message, retryable=retryable, retry_after_seconds=retry_after_seconds),
    )


def complete_job(job_id: str, result: dict) -> dict | None:
    return transition(job_id, "done", result=result, error=None)


def set_error_hint(job_id: str, code: str, message: str | None = None, *, retryable: bool = True,
                   retry_after_seconds: int | None = None) -> dict | None:
    job = get_job(job_id)
    if not job or job["status"] in TERMINAL:
        return None
    job["error"] = error_dict(code, message, retryable=retryable, retry_after_seconds=retry_after_seconds)
    job["updated_at"] = now_iso()
    _save(job)
    audit.append(job_id, job["status"], code, error_code=code)
    return job


def remember_transcript(job_id: str, *, file_hash: str | None, transcript_hash: str | None,
                        transcript_length: int | None, cache_flags: dict | None = None,
                        file_path: str | None = None, metadata: dict | None = None) -> dict | None:
    job = get_job(job_id)
    if not job or job["status"] in TERMINAL:
        return None
    if file_hash:
        job["file_hash"] = file_hash
    if transcript_hash:
        job["transcript_hash"] = transcript_hash
    if transcript_length is not None:
        job["transcript_length"] = transcript_length
    if cache_flags:
        flags = job.get("cache_flags") or {}
        flags.update(cache_flags)
        job["cache_flags"] = flags
    artifacts = job.setdefault("artifacts", {"file_path": None, "metadata": None})
    if file_path:
        artifacts["file_path"] = file_path
    if metadata is not None:
        artifacts["metadata"] = metadata
    job["updated_at"] = now_iso()
    _save(job)
    audit.append(job_id, job["status"], "transcript_ready")
    return job


def remember_artifacts(job_id: str, *, file_path: str | None, file_hash: str | None,
                       metadata: dict | None) -> dict | None:
    job = get_job(job_id)
    if not job or job["status"] in TERMINAL:
        return None
    artifacts = job.setdefault("artifacts", {"file_path": None, "metadata": None})
    artifacts["file_path"] = file_path
    artifacts["metadata"] = metadata
    if file_hash:
        job["file_hash"] = file_hash
    job["updated_at"] = now_iso()
    _save(job)
    return job


def attach_approval(job_id: str, approval: dict) -> dict | None:
    job = get_job(job_id)
    if not job:
        return None
    job["approval"] = {
        "id": approval["id"],
        "status": approval["status"],
        "expires_at": approval["expires_at"],
    }
    job["updated_at"] = now_iso()
    _save(job)
    return job


def increment_attempts(job_id: str | None, stage: str) -> int:
    if not job_id:
        return 1
    job = get_job(job_id)
    if not job:
        return 1
    if job["status"] in TERMINAL:
        return ATTEMPT_LIMIT
    attempts = job.setdefault("attempts", {})
    attempts[stage] = int(attempts.get(stage, 0)) + 1
    job["updated_at"] = now_iso()
    _save(job)
    return attempts[stage]


def reopen_for_resume(job_id: str) -> dict | None:
    job = get_job(job_id)
    if not job or job["status"] != "failed":
        return None
    error = job.get("error") or {}
    if not error.get("retryable"):
        return None
    if not job.get("file_hash") and not job.get("transcript_hash"):
        return None
    stamp = now_iso()
    job["status"] = "summarizing"
    job["error"] = None
    job["updated_at"] = stamp
    job["stage_timestamps"]["summarizing"] = stamp
    job["deadline_at"] = (datetime.now(timezone.utc) + timedelta(seconds=DEADLINE_SECONDS)).isoformat()
    redis_client.sadd(ACTIVE_KEY, job_id)
    _sync_resume_index(job)
    _save(job)
    audit.append(job_id, "summarizing", "resume")
    return job


def _resume_index_key(job: dict) -> str | None:
    summary_type = (job.get("input") or {}).get("summary_type")
    if job.get("platform") and job.get("episode_id") and summary_type:
        return f"resume:{job['platform']}:{job['episode_id']}:{summary_type}"
    return None


def _sync_resume_index(job: dict) -> None:
    key = _resume_index_key(job)
    if not key:
        return
    error = job.get("error") or {}
    resumable = (
        job.get("status") == "failed"
        and error.get("retryable")
        and (job.get("file_hash") or job.get("transcript_hash"))
    )
    if resumable:
        redis_client.set(key, job["job_id"], ex=JOB_TTL_SECONDS)
        return
    current = redis_client.get(key)
    if current == job["job_id"]:
        redis_client.delete(key)


def find_resumable(platform: str, episode_id: str, summary_type: str) -> dict | None:
    raw = redis_client.get(f"resume:{platform}:{episode_id}:{summary_type}")
    if not raw:
        return None
    job = get_job(raw)
    if not job or job.get("status") != "failed":
        return None
    error = job.get("error") or {}
    if not error.get("retryable"):
        return None
    if not job.get("file_hash") and not job.get("transcript_hash"):
        return None
    return job


def release_inflight(job: dict) -> None:
    platform = job.get("platform")
    episode_id = job.get("episode_id")
    summary_type = (job.get("input") or {}).get("summary_type")
    if not platform or not episode_id or not summary_type:
        return
    key = _inflight_key(platform, episode_id, summary_type)
    current = redis_client.get(key)
    if current == job["job_id"]:
        redis_client.delete(key)


def peek_inflight(platform: str, episode_id: str, summary_type: str) -> dict | None:
    raw = redis_client.get(_inflight_key(platform, episode_id, summary_type))
    if not raw:
        return None
    job = get_job(raw)
    if not job or job["status"] in TERMINAL:
        redis_client.delete(_inflight_key(platform, episode_id, summary_type))
        return None
    return job


def claim_inflight(platform: str, episode_id: str, summary_type: str, job_id: str) -> str | None:
    key = _inflight_key(platform, episode_id, summary_type)
    created = redis_client.set(key, job_id, nx=True, ex=JOB_TTL_SECONDS)
    if created:
        return None
    return redis_client.get(key)


def read_idempotency(operation: str, key: str, digest: str) -> tuple[str, str | None]:
    raw = redis_client.get(_idempotency_key(operation, key))
    if not raw:
        return "miss", None
    data = json.loads(raw)
    if data.get("body_hash") != digest:
        return "conflict", data.get("job_id")
    return "replay", data.get("job_id")


def bind_idempotency(operation: str, key: str, digest: str, job_id: str) -> str:
    redis_key = _idempotency_key(operation, key)
    payload = json.dumps({"job_id": job_id, "body_hash": digest})
    created = redis_client.set(redis_key, payload, nx=True, ex=IDEMPOTENCY_TTL_SECONDS)
    if created:
        return "created"
    action, _existing = read_idempotency(operation, key, digest)
    return action


def set_deadline(job_id: str) -> dict | None:
    job = get_job(job_id)
    if not job or job["status"] in TERMINAL:
        return None
    job["deadline_at"] = (datetime.now(timezone.utc) + timedelta(seconds=DEADLINE_SECONDS)).isoformat()
    job["updated_at"] = now_iso()
    _save(job)
    return job


def expire_if_needed(job: dict | None) -> dict | None:
    if not job or job["status"] in TERMINAL:
        return job
    if job["status"] == "awaiting_approval":
        expires_at = (job.get("approval") or {}).get("expires_at")
        if is_past(expires_at):
            updated = transition(
                job["job_id"],
                "expired",
                error=error_dict("approval_expired", retryable=False),
            )
            return updated or get_job(job["job_id"])
        return job
    if is_past(job.get("deadline_at")):
        updated = fail_job(job["job_id"], "timeout", retryable=True)
        return updated or get_job(job["job_id"])
    return job


def sweep_deadlines() -> list[str]:
    expired = []
    for job_id in list(redis_client.smembers(ACTIVE_KEY) or []):
        before = get_job(job_id)
        after = expire_if_needed(before)
        if after and before and after.get("status") != before.get("status") and after["status"] in TERMINAL:
            expired.append(job_id)
    return expired
