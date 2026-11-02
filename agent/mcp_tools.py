"""Product MCP tools that wrap the existing agent HTTP operations."""

from __future__ import annotations

import json
from typing import Any

from agent import jobs
from agent.errors import AgentError, HTTP_STATUS, error_dict
from agent.summarize import start_summarize
from redis_stream_client import SUMMARIZATION_GROUP, TRANSCRIPTION_GROUP, group_exists, redis_client

PROTOCOL_VERSION = "2025-03-26"
SERVER_NAME = "echobrief"
SERVER_VERSION = "1.0.0"
SERVER_INSTRUCTIONS = (
    "EchoBrief summarizes Apple Podcasts and Spotify episodes (bs/ns/ts). "
    "Use summarize_episode for work, get_job to poll, get_summary for cache-only reads, "
    "and get_health for liveness. Production is shared: prefer Idempotency-Key and "
    "cache_only/get_summary for dry reads. No OAuth; tools are public."
)


def _json_text(payload: Any) -> list[dict]:
    return [{"type": "text", "text": json.dumps(payload, default=str)}]


def _tool_error(exc: AgentError) -> dict:
    return {
        "content": _json_text(exc.as_body()),
        "isError": True,
        "structuredContent": exc.as_body(),
    }


def tool_definitions() -> list[dict]:
    return [
        {
            "name": "summarize_episode",
            "description": (
                "Summarize an Apple Podcasts or Spotify episode URL. Cache hits return "
                "status done; misses accept a job to poll with get_job. Optional "
                "idempotency_key coalesces retries. Set cache_only true to refuse misses."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Apple Podcasts or Spotify episode URL.",
                    },
                    "summary_type": {
                        "type": "string",
                        "enum": ["bs", "ns", "ts"],
                        "description": "bs bullet points, ns narrative, ts takeaways.",
                    },
                    "idempotency_key": {
                        "type": "string",
                        "description": "Optional Idempotency-Key for safe retries.",
                    },
                    "cache_only": {
                        "type": "boolean",
                        "description": "If true, return not_found on cache miss (no spend).",
                    },
                },
                "required": ["url", "summary_type"],
                "additionalProperties": False,
            },
            "annotations": {
                "title": "Summarize episode",
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            },
        },
        {
            "name": "get_job",
            "description": (
                "Read a durable summarize job by job_id until status is done, failed, "
                "cancelled, or expired. Safe to poll; no side effects."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job id from summarize_episode."},
                },
                "required": ["job_id"],
                "additionalProperties": False,
            },
            "annotations": {
                "title": "Get job",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        },
        {
            "name": "get_summary",
            "description": (
                "Read a cached episode summary by platform, episode_id, and summary_type. "
                "Does not start work or spend transcription/LLM quota."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "platform": {"type": "string", "enum": ["apple", "spotify"]},
                    "episode_id": {"type": "string"},
                    "summary_type": {"type": "string", "enum": ["bs", "ns", "ts"]},
                },
                "required": ["platform", "episode_id", "summary_type"],
                "additionalProperties": False,
            },
            "annotations": {
                "title": "Get cached summary",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        },
        {
            "name": "get_health",
            "description": (
                "Check resolver liveness, Redis ping, and whether transcription and "
                "summarization consumer groups exist."
            ),
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {
                "title": "Health check",
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        },
    ]


def call_tool(name: str, arguments: dict | None) -> dict:
    args = arguments or {}
    if name == "summarize_episode":
        return _summarize_episode(args)
    if name == "get_job":
        return _get_job(args)
    if name == "get_summary":
        return _get_summary(args)
    if name == "get_health":
        return _get_health()
    return {
        "content": _json_text({"error": {"code": "unknown_tool", "message": f"Unknown tool: {name}"}}),
        "isError": True,
    }


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


def _summarize_episode(args: dict) -> dict:
    url = args.get("url") or ""
    summary_type = args.get("summary_type") or ""
    idempotency_key = args.get("idempotency_key")
    cache_only = bool(args.get("cache_only"))
    try:
        result = start_summarize(
            url,
            summary_type,
            idempotency_key=idempotency_key,
            cache_only=cache_only,
        )
    except AgentError as exc:
        return _tool_error(exc)
    except Exception:
        return _tool_error(AgentError("internal", retryable=True))

    job = result.job
    if result.kind == "failed" and not job:
        body = {"error": error_dict("internal")}
        return {"content": _json_text(body), "isError": True, "structuredContent": body}
    if not job:
        return _tool_error(AgentError("internal"))
    body = jobs.public_view(job)
    body["http_status"] = _action_status(job)
    return {"content": _json_text(body), "structuredContent": body}


def _get_job(args: dict) -> dict:
    job_id = args.get("job_id") or ""
    if not job_id:
        return _tool_error(AgentError("invalid_input", "job_id is required.", retryable=False))
    jobs.sweep_deadlines()
    job = jobs.expire_if_needed(jobs.get_job(job_id))
    if not job:
        return _tool_error(AgentError("not_found", "Unknown job_id.", retryable=False))
    body = jobs.public_view(job)
    return {"content": _json_text(body), "structuredContent": body}


def _get_summary(args: dict) -> dict:
    platform = args.get("platform") or ""
    episode_id = args.get("episode_id") or ""
    summary_type = args.get("summary_type") or ""
    if summary_type not in ("bs", "ns", "ts") or platform not in ("apple", "spotify") or not episode_id:
        return _tool_error(AgentError("invalid_input", retryable=False))
    from cache_service import CacheService

    cached = CacheService.get_cached_episode(platform, episode_id, summary_type)
    if not cached:
        return _tool_error(AgentError("not_found", "No cached summary for that episode.", retryable=False))
    body = {
        "summary": cached.get("summary"),
        "metadata": cached.get("metadata"),
        "cached": True,
        "cached_at": cached.get("cached_at"),
        "platform": platform,
        "episode_id": episode_id,
        "summary_type": summary_type,
    }
    return {"content": _json_text(body), "structuredContent": body}


def _get_health() -> dict:
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
    return {"content": _json_text(body), "structuredContent": body}


def initialize_result() -> dict:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        "instructions": SERVER_INSTRUCTIONS,
    }
