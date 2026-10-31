"""Job store: transitions, late writes, idempotency, inflight coalesce, deadlines."""

from datetime import datetime, timedelta, timezone

from agent.errors import error_dict
from agent import jobs


def _job(**kwargs):
    defaults = dict(
        operation="summarize_episode",
        status="accepted",
        input_data={"url": "https://podcasts.apple.com/us/podcast/episode?i=1", "summary_type": "ts"},
        platform="apple",
        episode_id="1",
    )
    defaults.update(kwargs)
    return jobs.create_job(**defaults)


def test_allowed_transition_and_same_status_noop():
    job = _job()
    moved = jobs.transition(job["job_id"], "resolving")
    assert moved["status"] == "resolving"
    again = jobs.transition(job["job_id"], "resolving")
    assert again["job_id"] == job["job_id"]
    assert again["status"] == "resolving"


def test_late_write_does_not_overwrite_terminal_state():
    job = _job()
    jobs.transition(job["job_id"], "resolving")
    failed = jobs.fail_job(job["job_id"], "upstream_unavailable", retryable=True)
    assert failed["status"] == "failed"
    assert jobs.transition(job["job_id"], "done", result={"summary": "late"}) is None
    assert jobs.complete_job(job["job_id"], {"summary": "late"}) is None
    stored = jobs.get_job(job["job_id"])
    assert stored["status"] == "failed"
    assert stored["result"] is None


def test_idempotency_replay_and_conflict():
    digest = jobs.body_hash("https://example.test/a", "ts")
    other = jobs.body_hash("https://example.test/a", "ns")
    assert jobs.bind_idempotency("summarize_episode", "key-1", digest, "job-a") == "created"
    action, job_id = jobs.read_idempotency("summarize_episode", "key-1", digest)
    assert action == "replay"
    assert job_id == "job-a"
    assert jobs.bind_idempotency("summarize_episode", "key-1", digest, "job-b") == "replay"
    conflict, existing = jobs.read_idempotency("summarize_episode", "key-1", other)
    assert conflict == "conflict"
    assert existing == "job-a"


def test_inflight_coalesce():
    first = _job()
    assert jobs.claim_inflight("apple", "1", "ts", first["job_id"]) is None
    second = _job()
    holder = jobs.claim_inflight("apple", "1", "ts", second["job_id"])
    assert holder == first["job_id"]
    peeked = jobs.peek_inflight("apple", "1", "ts")
    assert peeked["job_id"] == first["job_id"]
    jobs.fail_job(first["job_id"], "timeout", retryable=True)
    assert jobs.peek_inflight("apple", "1", "ts") is None


def test_deadline_fails_job_and_ignores_approval_wait():
    job = _job()
    job["deadline_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    jobs.save_job(job)
    expired = jobs.expire_if_needed(jobs.get_job(job["job_id"]))
    assert expired["status"] == "failed"
    assert expired["error"]["code"] == "timeout"
    assert expired["error"]["retryable"] is True

    waiting = _job(status="awaiting_approval", with_deadline=False)
    waiting["deadline_at"] = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    jobs.save_job(waiting)
    untouched = jobs.expire_if_needed(jobs.get_job(waiting["job_id"]))
    assert untouched["status"] == "awaiting_approval"

    approval_job = _job(
        status="awaiting_approval",
        with_deadline=False,
        approval={"id": "appr", "status": "pending", "expires_at": (
            datetime.now(timezone.utc) - timedelta(seconds=5)
        ).isoformat()},
    )
    expired_approval = jobs.expire_if_needed(jobs.get_job(approval_job["job_id"]))
    assert expired_approval["status"] == "expired"
    assert expired_approval["error"]["code"] == "approval_expired"


def test_reopen_for_resume_requires_retryable_hash():
    permanent = _job(status="failed", with_deadline=False, error=error_dict("episode_not_found", retryable=False))
    permanent["file_hash"] = "abc"
    jobs.save_job(permanent)
    assert jobs.reopen_for_resume(permanent["job_id"]) is None

    retryable = _job(status="failed", with_deadline=False, error=error_dict("upstream_unavailable", retryable=True))
    assert jobs.reopen_for_resume(retryable["job_id"]) is None
    retryable = jobs.get_job(retryable["job_id"])
    retryable["transcript_hash"] = "deadbeef"
    jobs.save_job(retryable)
    resumed = jobs.reopen_for_resume(retryable["job_id"])
    assert resumed["status"] == "summarizing"
    assert resumed["error"] is None
    assert jobs.transition(resumed["job_id"], "resolving") is None
