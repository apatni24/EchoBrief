"""Append-only audit list per job. Stdout is one JSON object per event."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from redis_stream_client import redis_client

AUDIT_TTL_SECONDS = 7 * 24 * 60 * 60


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(job_id: str | None, stage: str, event: str) -> None:
    print(json.dumps({"job_id": job_id, "stage": stage, "event": event}), flush=True)


def append(job_id: str | None, stage: str, event: str, error_code: str | None = None) -> dict:
    entry = {"ts": _now(), "stage": stage, "event": event, "error_code": error_code}
    log_event(job_id, stage, event)
    if not job_id:
        return entry
    key = f"audit:{job_id}"
    redis_client.rpush(key, json.dumps(entry))
    redis_client.expire(key, AUDIT_TTL_SECONDS)
    return entry


def read(job_id: str) -> list[dict]:
    raw_entries = redis_client.lrange(f"audit:{job_id}", 0, -1) or []
    entries = []
    for raw in raw_entries:
        if isinstance(raw, bytes):
            raw = raw.decode()
        entries.append(json.loads(raw))
    return entries
