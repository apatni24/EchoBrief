"""Shared summarize entry point for POST /submit and the agent route."""

from __future__ import annotations

from dataclasses import dataclass

import podcast_audio_resolver_service.audio_upload_producer as audio_upload_producer
import podcast_audio_resolver_service.get_audio as get_audio
import transcription_service.transcription_complete_producer as transcription_complete_producer
from agent import approvals, jobs
from agent.errors import (
    HUMAN_APPROVAL,
    HUMAN_AUDIO_MISSING,
    HUMAN_BAD_PLATFORM,
    HUMAN_BAD_SUMMARY,
    HUMAN_INTERNAL,
    HUMAN_METADATA_MISSING,
    HUMAN_PROCESS_FAILED,
    HUMAN_PUBLISH_FAILED,
    HUMAN_URL_REQUIRED,
    AgentError,
    MESSAGES,
    classify_resolver_message,
    error_dict,
)
from agent.policies import evaluate, increment_uncached_budget
from cache_service import CacheService


@dataclass
class StartResult:
    kind: str
    job: dict | None = None
    human_body: dict | None = None
    data: dict | None = None


def _human_error(message: str) -> dict:
    return {"message": message, "error": True, "data": None, "cached": False}


def _human_progress(job: dict, data: dict | None = None) -> dict:
    if data is None:
        artifacts = job.get("artifacts") or {}
        data = {
            "job_id": job["job_id"],
            "platform": job.get("platform"),
            "episode_id": job.get("episode_id"),
            "summary_type": (job.get("input") or {}).get("summary_type"),
        }
        if artifacts.get("file_path"):
            data["file_path"] = artifacts["file_path"]
        if artifacts.get("metadata"):
            data["metadata"] = artifacts["metadata"]
    return {"message": "Download successful", "data": data, "error": False, "cached": False}


def _human_cache(cached: dict) -> dict:
    return {
        "message": "Cached result retrieved",
        "data": cached,
        "error": False,
        "cached": True,
        "processing_time": 0,
    }


def _human_approval(job: dict) -> dict:
    approval = job.get("approval") or {}
    return {
        "message": HUMAN_APPROVAL,
        "error": True,
        "data": {
            "job_id": job["job_id"],
            "approval_id": approval.get("id"),
            "status": "awaiting_approval",
        },
        "cached": False,
    }


def _result_from_job(job: dict, *, kind: str | None = None, data: dict | None = None) -> StartResult:
    status = job.get("status")
    if status == "done" and (job.get("result") or {}).get("cached"):
        cached = {
            "summary": (job.get("result") or {}).get("summary"),
            "metadata": (job.get("result") or {}).get("metadata"),
            "cached_at": (job.get("result") or {}).get("cached_at"),
            "platform": job.get("platform"),
            "episode_id": job.get("episode_id"),
            "summary_type": (job.get("input") or {}).get("summary_type"),
        }
        return StartResult(kind="cache_hit", job=job, human_body=_human_cache(cached))
    if status == "awaiting_approval":
        return StartResult(kind="awaiting_approval", job=job, human_body=_human_approval(job))
    if status == "failed":
        message = ((job.get("error") or {}).get("message")) or HUMAN_PROCESS_FAILED
        code = (job.get("error") or {}).get("code")
        if code == "episode_too_long":
            message = "Episode is longer than 30 minutes. Only shorter episodes are supported currently."
        elif code == "upstream_unavailable":
            message = HUMAN_PUBLISH_FAILED if "publish" in message.lower() else message
        return StartResult(kind="failed", job=job, human_body=_human_error(message))
    if status in ("cancelled", "expired"):
        return StartResult(kind="failed", job=job, human_body=_human_error(MESSAGES.get(
            (job.get("error") or {}).get("code"), HUMAN_INTERNAL
        )))
    resolved_kind = kind or ("joined" if status != "accepted" else "accepted")
    return StartResult(kind=resolved_kind, job=job, human_body=_human_progress(job, data), data=data)


def _bind(idempotency_key: str | None, digest: str, job_id: str) -> None:
    if not idempotency_key:
        return
    action = jobs.bind_idempotency("summarize_episode", idempotency_key, digest, job_id)
    if action == "conflict":
        raise AgentError("idempotency_conflict", retryable=False)


def _load_transcript(job: dict) -> str | None:
    file_hash = job.get("file_hash")
    if file_hash:
        cached = CacheService.get_cached_transcript_by_hash(file_hash)
        if cached and cached.get("transcript"):
            return cached["transcript"]
    content_hash = job.get("transcript_hash")
    if content_hash:
        cached = CacheService.get_cached_transcript_by_content_hash(content_hash)
        if cached and cached.get("transcript"):
            return cached["transcript"]
    return None


def resume_job(job_id: str) -> StartResult | None:
    job = jobs.reopen_for_resume(job_id)
    if not job:
        return None
    transcript = _load_transcript(job)
    if not transcript:
        failed = jobs.fail_job(
            job["job_id"],
            "upstream_unavailable",
            "Transcript cache missed on resume.",
            retryable=False,
        )
        return StartResult(kind="failed", job=failed or jobs.get_job(job_id), human_body=_human_error(HUMAN_PROCESS_FAILED))
    metadata = (job.get("artifacts") or {}).get("metadata") or {}
    payload = {
        "job_id": job["job_id"],
        "summary_type": (job.get("input") or {}).get("summary_type"),
        "transcript": transcript,
        "metadata": metadata,
        "platform": job.get("platform"),
        "episode_id": job.get("episode_id"),
        "file_path": (job.get("artifacts") or {}).get("file_path") or "",
        "file_hash": job.get("file_hash"),
        "processing_time": 0,
    }
    try:
        transcription_complete_producer.emit_transcription_completed(payload)
    except Exception:
        failed = jobs.fail_job(job["job_id"], "upstream_unavailable", retryable=True)
        return StartResult(
            kind="failed",
            job=failed or jobs.get_job(job_id),
            human_body=_human_error(HUMAN_PUBLISH_FAILED),
        )
    current = jobs.get_job(job["job_id"]) or job
    return _result_from_job(current, kind="accepted")


def _from_cache(cached: dict, url: str, summary_type: str, platform: str, episode_id: str,
                idempotency_key: str | None, digest: str) -> StartResult:
    if "platform" not in cached:
        cached["platform"] = platform
    if "episode_id" not in cached:
        cached["episode_id"] = episode_id
    if "summary_type" not in cached:
        cached["summary_type"] = summary_type
    result = {
        "summary": cached.get("summary"),
        "metadata": cached.get("metadata"),
        "cached": True,
        "cached_at": cached.get("cached_at"),
    }
    job = jobs.create_job(
        operation="summarize_episode",
        status="done",
        input_data={"url": url, "summary_type": summary_type},
        platform=platform,
        episode_id=episode_id,
        idempotency_key=idempotency_key,
        with_deadline=False,
        result=result,
    )
    job["cache_flags"] = {"episode": True, "transcript": False, "file": False}
    job["transcript_length"] = cached.get("transcript_length")
    jobs.save_job(job)
    _bind(idempotency_key, digest, job["job_id"])
    return StartResult(kind="cache_hit", job=job, human_body=_human_cache(cached))


def _awaiting(input_data, platform, episode_id, idempotency_key, digest, decision) -> StartResult:
    job = jobs.create_job(
        operation="summarize_episode",
        status="awaiting_approval",
        input_data=input_data,
        platform=platform,
        episode_id=episode_id,
        idempotency_key=idempotency_key,
        with_deadline=False,
    )
    other = jobs.claim_inflight(platform, episode_id, summary_type=input_data["summary_type"], job_id=job["job_id"])
    if other and other != job["job_id"]:
        jobs.transition(job["job_id"], "cancelled")
        winner = jobs.get_job(other)
        if winner:
            _bind(idempotency_key, digest, winner["job_id"])
            return _result_from_job(winner, kind="joined")
    approval = approvals.create_approval(
        "summarize_episode",
        input_data,
        job["job_id"],
        decision.expires_in_seconds or 900,
    )
    if approval["job_id"] != job["job_id"]:
        jobs.transition(job["job_id"], "cancelled")
        existing = jobs.get_job(approval["job_id"])
        if existing:
            _bind(idempotency_key, digest, existing["job_id"])
            return _result_from_job(existing, kind="awaiting_approval")
    jobs.attach_approval(job["job_id"], approval)
    _bind(idempotency_key, digest, job["job_id"])
    current = jobs.get_job(job["job_id"]) or job
    return _result_from_job(current, kind="awaiting_approval")


def _fail_resolver(job: dict, message: str) -> StartResult:
    code = classify_resolver_message(message)
    failed = jobs.fail_job(job["job_id"], code, MESSAGES.get(code), retryable=code == "upstream_unavailable")
    human_message = message or HUMAN_PROCESS_FAILED
    if code == "upstream_unavailable" and message == HUMAN_PUBLISH_FAILED:
        human_message = HUMAN_PUBLISH_FAILED
    return StartResult(kind="failed", job=failed or jobs.get_job(job["job_id"]), human_body=_human_error(human_message))


def _start_work(job: dict, url: str) -> StartResult:
    if job.get("status") == "accepted":
        moved = jobs.transition(job["job_id"], "resolving")
        job = moved or jobs.get_job(job["job_id"]) or job
    if job.get("status") != "resolving":
        return _result_from_job(job)
    platform = job.get("platform")
    summary_type = (job.get("input") or {}).get("summary_type")
    try:
        if "podcasts.apple.com" in url:
            data = get_audio.get_episode_audio_from_apple(url)
        elif "open.spotify.com" in url:
            data = get_audio.get_episode_audio_from_spotify(url)
        else:
            return _fail_resolver(job, HUMAN_BAD_PLATFORM)
    except Exception:
        return _fail_resolver(job, HUMAN_PROCESS_FAILED)

    if data is None:
        return _fail_resolver(job, HUMAN_PROCESS_FAILED)
    if isinstance(data, dict) and data.get("error"):
        return _fail_resolver(job, data["error"])
    if not data.get("file_path"):
        return _fail_resolver(job, HUMAN_AUDIO_MISSING)
    if not data.get("metadata"):
        return _fail_resolver(job, HUMAN_METADATA_MISSING)

    duration = (data.get("metadata") or {}).get("duration")
    decision = evaluate(
        "summarize_episode",
        duration_seconds=duration,
        skip_budget=True,
    )
    if decision.effect == "deny":
        failed = jobs.fail_job(job["job_id"], decision.error_code or "episode_too_long", retryable=False)
        return StartResult(
            kind="failed",
            job=failed or jobs.get_job(job["job_id"]),
            human_body=_human_error(
                "Episode is longer than 30 minutes. Only shorter episodes are supported currently."
            ),
        )

    data = dict(data)
    data["summary_type"] = summary_type
    data["job_id"] = job["job_id"]
    data["platform"] = platform
    data["episode_id"] = job.get("episode_id")
    jobs.remember_artifacts(
        job["job_id"],
        file_path=data.get("file_path"),
        file_hash=data.get("file_hash"),
        metadata=data.get("metadata"),
    )
    try:
        audio_upload_producer.emit_audio_uploaded(data)
    except Exception:
        failed = jobs.fail_job(job["job_id"], "upstream_unavailable", retryable=True)
        return StartResult(
            kind="failed",
            job=failed or jobs.get_job(job["job_id"]),
            human_body=_human_error(HUMAN_PUBLISH_FAILED),
        )
    increment_uncached_budget()
    current = jobs.get_job(job["job_id"]) or job
    return StartResult(kind="accepted", job=current, human_body=_human_progress(current, data), data=data)


def start_summarize(url: str, summary_type: str, idempotency_key: str | None = None) -> StartResult:
    url = (url or "").strip()
    if not url:
        raise AgentError("invalid_input", human_detail=HUMAN_URL_REQUIRED, retryable=False)
    if not summary_type or summary_type not in ("ts", "ns", "bs"):
        raise AgentError(
            "invalid_input",
            "summary_type must be one of bs, ns, or ts.",
            human_detail=HUMAN_BAD_SUMMARY,
            retryable=False,
        )
    platform = CacheService.get_platform(url)
    episode_id = CacheService.extract_episode_id(url)
    if platform == "unknown" or not episode_id:
        raise AgentError("unsupported_platform", human_detail=HUMAN_BAD_PLATFORM, retryable=False)

    digest = jobs.body_hash(url, summary_type)
    input_data = {"url": url, "summary_type": summary_type}

    if idempotency_key:
        action, existing_id = jobs.read_idempotency("summarize_episode", idempotency_key, digest)
        if action == "conflict":
            raise AgentError("idempotency_conflict", retryable=False)
        if action == "replay" and existing_id:
            existing = jobs.get_job(existing_id)
            if existing and existing.get("status") == "failed":
                resumed = resume_job(existing["job_id"])
                if resumed:
                    return resumed
            if existing:
                return _result_from_job(existing, kind="joined")

    cached = CacheService.get_cached_episode(platform, episode_id, summary_type)
    if cached:
        return _from_cache(cached, url, summary_type, platform, episode_id, idempotency_key, digest)

    inflight = jobs.peek_inflight(platform, episode_id, summary_type)
    if inflight:
        _bind(idempotency_key, digest, inflight["job_id"])
        return _result_from_job(inflight, kind="joined")

    resumable = jobs.find_resumable(platform, episode_id, summary_type)
    if resumable:
        resumed = resume_job(resumable["job_id"])
        if resumed:
            _bind(idempotency_key, digest, resumable["job_id"])
            return resumed

    decision = evaluate("summarize_episode", episode_cache_hit=False)
    if decision.effect == "pending":
        return _awaiting(input_data, platform, episode_id, idempotency_key, digest, decision)
    if decision.effect == "deny":
        job = jobs.create_job(
            operation="summarize_episode",
            status="failed",
            input_data=input_data,
            platform=platform,
            episode_id=episode_id,
            idempotency_key=idempotency_key,
            with_deadline=False,
            error=error_dict(decision.error_code or "episode_too_long", retryable=False),
        )
        _bind(idempotency_key, digest, job["job_id"])
        return StartResult(
            kind="failed",
            job=job,
            human_body=_human_error(
                "Episode is longer than 30 minutes. Only shorter episodes are supported currently."
            ),
        )

    job = jobs.create_job(
        operation="summarize_episode",
        status="accepted",
        input_data=input_data,
        platform=platform,
        episode_id=episode_id,
        idempotency_key=idempotency_key,
    )
    _bind(idempotency_key, digest, job["job_id"])
    other = jobs.claim_inflight(platform, episode_id, summary_type, job["job_id"])
    if other and other != job["job_id"]:
        jobs.transition(job["job_id"], "cancelled")
        winner = jobs.get_job(other)
        if winner:
            return _result_from_job(winner, kind="joined")
    return _start_work(job, url)


def continue_approved_summarize(_args: dict, job_id: str) -> None:
    job = jobs.get_job(job_id)
    if not job or job.get("status") != "awaiting_approval":
        return
    moved = jobs.transition(job_id, "resolving")
    if not moved:
        return
    jobs.set_deadline(job_id)
    current = jobs.get_job(job_id) or moved
    url = (current.get("input") or {}).get("url") or ""
    _start_work(current, url)


approvals.register_runner("summarize_episode", continue_approved_summarize)
