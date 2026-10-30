"""Capability catalog. HTTP routes are a projection of these definitions."""

from __future__ import annotations

SUMMARY_TYPE_SCHEMA = {
    "type": "string",
    "enum": ["bs", "ns", "ts"],
    "description": "bs: bullet points. ns: narrative. ts: takeaways.",
}

ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "code": {"type": "string"},
        "message": {"type": "string"},
        "retryable": {"type": "boolean"},
        "retry_after_seconds": {"type": ["integer", "null"]},
    },
    "required": ["code", "message", "retryable", "retry_after_seconds"],
}

JOB_SCHEMA = {
    "type": "object",
    "properties": {
        "job_id": {"type": "string"},
        "operation": {"type": "string"},
        "status": {
            "type": "string",
            "enum": [
                "accepted",
                "resolving",
                "transcribing",
                "summarizing",
                "done",
                "failed",
                "cancelled",
                "expired",
                "awaiting_approval",
            ],
        },
        "result": {"type": ["object", "null"]},
        "error": {"anyOf": [ERROR_SCHEMA, {"type": "null"}]},
        "poll_url": {"type": "string"},
        "cached": {"type": "boolean"},
    },
}

SUMMARIZE_ERRORS = [
    "invalid_input",
    "unsupported_platform",
    "episode_too_long",
    "episode_not_found",
    "upstream_unavailable",
    "timeout",
    "rate_limited",
    "approval_required",
    "idempotency_conflict",
    "internal",
    "audio_missing",
]

KNOWN_LIMITS = [
    "Episodes whose itunes_duration is over 1800 seconds are denied with episode_too_long. "
    "duration_to_seconds expects HH:MM:SS. A one-part or two-part itunes_duration is caught and "
    "may skip the 30-minute cap, so an agent must not assume every long episode is rejected.",
    "The uncached summarize budget is global. It is not a per-caller quota.",
    "Approval ids are unauthenticated capability URLs: UUID4, single use, 15-minute TTL. "
    "The decision route is a human operation.",
]


def _op(**kwargs) -> dict:
    return kwargs


OPERATIONS = [
    _op(
        id="summarize_episode",
        title="Summarize an episode",
        description=(
            "Summarize an Apple Podcasts or Spotify episode. A cache hit returns the stored "
            "summary synchronously. A miss downloads the enclosure, transcribes with AssemblyAI, "
            "and summarizes with OpenRouter (three LLM calls: speaker roles, transcript check, "
            "summary). Cache hits do not spend those APIs. Over 1800 seconds is a hard deny. "
            "Poll poll_url until done, failed, cancelled, or expired. The WebSocket is only a "
            "hint for the human UI."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Apple Podcasts or Spotify episode URL."},
                "summary_type": SUMMARY_TYPE_SCHEMA,
            },
            "required": ["url", "summary_type"],
        },
        output_schema=JOB_SCHEMA,
        invocation={"method": "POST", "path": "/agent/v1/episodes/summaries"},
        mode="async",
        effects=["network", "disk", "redis", "paid_api", "cache_write"],
        effect_details=[
            "Podcast Index API",
            "Show RSS feed (rss_cache/*.xml)",
            "Enclosure audio download (audio_files/)",
            "AssemblyAI transcription",
            "OpenRouter chat completions",
            "Redis streams audio_uploaded and transcription_complete",
            "Redis episode and transcript caches",
        ],
        risk="spend",
        idempotency=(
            "Header Idempotency-Key. The same key and body returns the same job. "
            "The same key and a different body returns 409 idempotency_conflict. "
            "Overlapping misses for the same episode and summary type share one in-flight job."
        ),
        timeout_seconds=240,
        approval_policy="uncached-summarize-budget",
        errors=SUMMARIZE_ERRORS,
        audience="agent",
    ),
    _op(
        id="get_job",
        title="Read a job",
        description="Read the durable job record, including terminal state after the WebSocket is gone.",
        input_schema={
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
        output_schema=JOB_SCHEMA,
        invocation={"method": "GET", "path": "/agent/v1/jobs/{job_id}"},
        mode="sync",
        effects=["redis"],
        effect_details=["Redis read of job:{job_id}"],
        risk="read",
        idempotency="Safe to retry. Does not start work.",
        timeout_seconds=5,
        approval_policy=None,
        errors=["not_found", "timeout", "rate_limited"],
        audience="agent",
    ),
    _op(
        id="get_job_audit",
        title="Read a job audit trail",
        description="Stage transitions for one job. Does not include transcript text.",
        input_schema={
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
        output_schema={
            "type": "object",
            "properties": {"job_id": {"type": "string"}, "audit": {"type": "array"}},
        },
        invocation={"method": "GET", "path": "/agent/v1/jobs/{job_id}/audit"},
        mode="sync",
        effects=["redis"],
        effect_details=["Redis list audit:{job_id}"],
        risk="read",
        idempotency="Safe to retry.",
        timeout_seconds=5,
        approval_policy=None,
        errors=["not_found"],
        audience="agent",
    ),
    _op(
        id="get_summary",
        title="Read a cached summary",
        description="Read episode:{platform}:{episode_id}:{summary_type}. Does not start a job.",
        input_schema={
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["apple", "spotify"]},
                "episode_id": {"type": "string"},
                "summary_type": SUMMARY_TYPE_SCHEMA,
            },
            "required": ["platform", "episode_id", "summary_type"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "metadata": {"type": "object"},
                "cached": {"type": "boolean"},
                "cached_at": {"type": "number"},
            },
        },
        invocation={
            "method": "GET",
            "path": "/agent/v1/summaries?platform={platform}&episode_id={episode_id}&summary_type={summary_type}",
        },
        mode="sync",
        effects=["redis"],
        effect_details=["Redis read of the episode cache key"],
        risk="read",
        idempotency="Safe to retry. Does not start work.",
        timeout_seconds=5,
        approval_policy=None,
        errors=["invalid_input", "not_found"],
        audience="agent",
    ),
    _op(
        id="get_health",
        title="Health",
        description="Resolver liveness, a Redis ping, and whether the transcription and summarization consumer groups exist.",
        input_schema={"type": "object", "properties": {}},
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "redis": {"type": "string"},
                "consumer_groups": {"type": "object"},
            },
        },
        invocation={"method": "GET", "path": "/health"},
        mode="sync",
        effects=["redis"],
        effect_details=["Redis PING and XINFO GROUPS"],
        risk="read",
        idempotency="Safe to retry.",
        timeout_seconds=5,
        approval_policy=None,
        errors=["upstream_unavailable"],
        audience="agent",
    ),
    _op(
        id="retry_job",
        title="Resume a failed summarize",
        description=(
            "If summarization failed after a transcript was cached, resume that job at "
            "summarizing. Does not re-download or re-transcribe."
        ),
        input_schema={
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
        output_schema=JOB_SCHEMA,
        invocation={"method": "POST", "path": "/agent/v1/jobs/{job_id}/retry"},
        mode="async",
        effects=["network", "redis", "paid_api"],
        effect_details=["OpenRouter only, when the transcript cache still holds the text"],
        risk="spend",
        idempotency="Retrying a job that is not a retryable summarizing failure returns the current job.",
        timeout_seconds=240,
        approval_policy=None,
        errors=["not_found", "invalid_input", "upstream_unavailable"],
        audience="agent",
    ),
    _op(
        id="invalidate_episode_cache",
        title="Invalidate one episode cache entry",
        description=(
            "Delete one episode cache key. The next summarize is a paid miss. "
            "Does not run until an approval for that argument hash is approved and unexpired."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "platform": {"type": "string"},
                "episode_id": {"type": "string"},
                "summary_type": SUMMARY_TYPE_SCHEMA,
            },
            "required": ["platform", "episode_id", "summary_type"],
        },
        output_schema=JOB_SCHEMA,
        invocation={
            "method": "DELETE",
            "path": "/cache/invalidate/{platform}/{episode_id}/{summary_type}",
        },
        mode="sync",
        effects=["redis", "cache_delete"],
        effect_details=["Deletes episode:{platform}:{episode_id}:{summary_type}"],
        risk="costly_destructive",
        idempotency="A repeated call joins the pending approval for the same arguments.",
        timeout_seconds=15,
        approval_policy="invalidate-requires-approval",
        errors=["approval_required", "approval_expired", "invalid_input"],
        audience="agent",
    ),
    _op(
        id="clear_cache",
        title="Clear episode and transcript caches",
        description=(
            "Delete every episode and transcript cache key. Requires approval. "
            "This route does not accept an admin key. The legacy DELETE /cache/clear "
            "admin key is not an agent tool."
        ),
        input_schema={"type": "object", "properties": {}},
        output_schema=JOB_SCHEMA,
        invocation={"method": "POST", "path": "/agent/v1/cache/clear"},
        mode="sync",
        effects=["redis", "cache_delete"],
        effect_details=["Deletes episode:* and transcript:* keys"],
        risk="destructive",
        idempotency="A repeated call joins the pending clear approval.",
        timeout_seconds=30,
        approval_policy="clear-requires-approval",
        errors=["approval_required", "approval_expired"],
        audience="agent",
    ),
    _op(
        id="get_cache_stats",
        title="Cache statistics",
        description="Hit and miss counters plus maintained cache counts. Does not scan Redis with KEYS.",
        input_schema={"type": "object", "properties": {}},
        output_schema={
            "type": "object",
            "properties": {
                "episode_cache_count": {"type": "integer"},
                "transcript_cache_count": {"type": "integer"},
                "file_hash_cache_count": {"type": "integer"},
                "total_cached_items": {"type": "integer"},
                "episode_cache_hits": {"type": "integer"},
                "episode_cache_misses": {"type": "integer"},
                "episode_cache_hit_ratio": {"type": ["number", "null"]},
            },
        },
        invocation={"method": "GET", "path": "/cache/stats"},
        mode="sync",
        effects=["redis"],
        effect_details=["Reads maintained integer counters"],
        risk="read",
        idempotency="Safe to retry.",
        timeout_seconds=5,
        approval_policy=None,
        errors=["upstream_unavailable"],
        audience="agent",
    ),
]

HUMAN_OPERATIONS = [
    _op(
        id="decide_approval",
        title="Decide a pending approval",
        description=(
            "Human operation. Approve runs the pending operation once. "
            "A second approve returns the same job and does not run it again. "
            "Deny or a late decision does not run side effects. Not an agent tool."
        ),
        input_schema={
            "type": "object",
            "properties": {"decision": {"type": "string", "enum": ["approve", "deny"]}},
            "required": ["decision"],
        },
        output_schema=JOB_SCHEMA,
        invocation={"method": "POST", "path": "/agent/v1/approvals/{approval_id}/decision"},
        mode="sync",
        effects=["redis"],
        effect_details=["Updates approval:{id}. Approve then runs the gated operation once."],
        risk="compute",
        idempotency="Single use. A repeated approve is a no-op.",
        timeout_seconds=15,
        approval_policy=None,
        errors=["not_found", "approval_expired", "invalid_input"],
        audience="human",
    ),
]


def all_operations() -> list[dict]:
    return OPERATIONS + HUMAN_OPERATIONS


def find_operation(operation_id: str) -> dict | None:
    for operation in all_operations():
        if operation["id"] == operation_id:
            return operation
    return None


def openapi_extras(operation_id: str) -> dict:
    operation = find_operation(operation_id)
    if not operation:
        return {}
    return {
        "x-echobrief-effects": list(operation["effects"]),
        "x-echobrief-risk": operation["risk"],
        "x-echobrief-approval-policy": operation.get("approval_policy"),
        "x-echobrief-operation": operation_id,
    }


def build_capabilities() -> dict:
    return {
        "name": "echobrief",
        "protocol": "echobrief-capabilities",
        "version": "1",
        "known_limits": KNOWN_LIMITS,
        "error_schema": ERROR_SCHEMA,
        "operations": OPERATIONS,
        "human_operations": HUMAN_OPERATIONS,
    }
