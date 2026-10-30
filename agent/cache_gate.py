"""Approval gate for cache deletion. New code does not read ADMIN_CACHE_KEY."""

from __future__ import annotations

from agent import approvals, jobs
from agent.policies import evaluate
from cache_service import CacheService


def _pending_response(job: dict, approval: dict, message: str) -> dict:
    return {
        "success": False,
        "status": "awaiting_approval",
        "approval_id": approval["id"],
        "job_id": job["job_id"],
        "message": message,
        "poll_url": f"/agent/v1/jobs/{job['job_id']}",
    }


def request_invalidate(platform: str, episode_id: str, summary_type: str) -> dict:
    decision = evaluate("invalidate_episode_cache")
    args = {"platform": platform, "episode_id": episode_id, "summary_type": summary_type}
    job = jobs.create_job(
        operation="invalidate_episode_cache",
        status="awaiting_approval",
        input_data=args,
        platform=platform,
        episode_id=episode_id,
        with_deadline=False,
    )
    approval = approvals.create_approval(
        "invalidate_episode_cache",
        args,
        job["job_id"],
        decision.expires_in_seconds or 900,
    )
    # A repeated call returns the existing pending approval, which may point at an older job.
    if approval["job_id"] != job["job_id"]:
        jobs.transition(job["job_id"], "cancelled")
        existing = jobs.get_job(approval["job_id"])
        return _pending_response(existing or job, approval, "Approval required before this cache entry can be invalidated.")
    jobs.attach_approval(job["job_id"], approval)
    job = jobs.get_job(job["job_id"]) or job
    return _pending_response(job, approval, "Approval required before this cache entry can be invalidated.")


def execute_invalidate(args: dict, job_id: str) -> dict:
    platform = args.get("platform") or ""
    episode_id = args.get("episode_id") or ""
    summary_type = args.get("summary_type") or ""
    success = CacheService.invalidate_specific_episode(platform, episode_id, summary_type)
    result = {
        "success": bool(success),
        "message": f"Cache invalidated for {platform}:{episode_id}:{summary_type}",
        "cached": False,
    }
    jobs.complete_job(job_id, result)
    return result


def request_clear() -> dict:
    decision = evaluate("clear_cache")
    args = {"target": "all"}
    job = jobs.create_job(
        operation="clear_cache",
        status="awaiting_approval",
        input_data=args,
        with_deadline=False,
    )
    approval = approvals.create_approval(
        "clear_cache",
        args,
        job["job_id"],
        decision.expires_in_seconds or 900,
    )
    if approval["job_id"] != job["job_id"]:
        jobs.transition(job["job_id"], "cancelled")
        existing = jobs.get_job(approval["job_id"])
        return _pending_response(existing or job, approval, "Approval required before the cache can be cleared.")
    jobs.attach_approval(job["job_id"], approval)
    job = jobs.get_job(job["job_id"]) or job
    return _pending_response(job, approval, "Approval required before the cache can be cleared.")


def execute_clear(_args: dict, job_id: str) -> dict:
    success = CacheService.clear_cache()
    result = {"success": bool(success), "message": "Cache cleared successfully", "cached": False}
    jobs.complete_job(job_id, result)
    return result


approvals.register_runner("invalidate_episode_cache", execute_invalidate)
approvals.register_runner("clear_cache", execute_clear)
