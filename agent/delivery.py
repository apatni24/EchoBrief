"""Consumer-group delivery: ack after the stage is persisted, dead-letter after three tries."""

from __future__ import annotations

import asyncio
import inspect
import json
import time

from agent import jobs
from agent.audit import log_event
from redis_stream_client import (
    JOBS_DLQ_STREAM,
    ack as ack_message,
    autoclaim as autoclaim_messages,
    ensure_consumer_group,
    read_group,
    redis_client,
)

MAX_ATTEMPTS = jobs.ATTEMPT_LIMIT


def ack(stream: str, group: str, message_id: str | None) -> None:
    if message_id:
        ack_message(stream, group, message_id)


def claim_pending(stream: str, group: str, consumer: str):
    try:
        result = autoclaim_messages(stream, group, consumer)
    except Exception:
        return []
    if not result or len(result) < 2:
        return []
    return result[1] or []


def read_new(stream: str, group: str, consumer: str):
    try:
        messages = read_group(stream, group, consumer)
    except Exception as exc:
        log_event(None, group, "read_failed")
        raise exc
    if not messages:
        return []
    entries = []
    for _stream, batch in messages:
        entries.extend(batch)
    return entries


def publish_dlq(entry: dict, code: str, job_id: str | None) -> None:
    payload = dict(entry)
    payload["error_code"] = code
    payload["job_id"] = job_id
    payload.pop("transcript", None)
    redis_client.xadd(JOBS_DLQ_STREAM, {"data": json.dumps(payload)})


def fail_stage(*, job_id: str | None, stage: str, code: str, message: str, retryable: bool,
               stream: str, group: str, message_id: str | None, entry: dict,
               retry_after_seconds: int | None = None) -> str:
    attempts = jobs.increment_attempts(job_id, stage) if job_id else 1
    give_up = (not retryable) or attempts >= MAX_ATTEMPTS
    if not give_up:
        if job_id:
            jobs.set_error_hint(
                job_id,
                code,
                message,
                retryable=True,
                retry_after_seconds=retry_after_seconds,
            )
        return "pending"
    publish_dlq(entry, code, job_id)
    if job_id:
        jobs.fail_job(
            job_id,
            code,
            message,
            retryable=retryable,
            retry_after_seconds=retry_after_seconds,
        )
    ack(stream, group, message_id)
    return "acked"


def _parse_fields(fields: dict) -> dict | None:
    raw = fields.get("data") if isinstance(fields, dict) else None
    if raw is None and isinstance(fields, dict):
        raw = fields.get(b"data")
    if isinstance(raw, bytes):
        raw = raw.decode()
    if not raw:
        return None
    return json.loads(raw)


def dispatch(handler, fields, message_id, loop, stream, group):
    try:
        parsed = _parse_fields(fields)
    except Exception:
        publish_dlq({"reason": "invalid_json"}, "invalid_input", None)
        ack(stream, group, message_id)
        return
    if parsed is None:
        publish_dlq({"reason": "empty"}, "invalid_input", None)
        ack(stream, group, message_id)
        return
    if inspect.iscoroutinefunction(handler):
        future = asyncio.run_coroutine_threadsafe(handler(parsed, message_id), loop)
        future.result()
        return
    handler(parsed, message_id, loop)


def consume_loop(stream: str, group: str, consumer_name: str, handler, loop) -> None:
    ensure_consumer_group(stream, group)
    while True:
        try:
            jobs.sweep_deadlines()
            for message_id, fields in claim_pending(stream, group, consumer_name):
                dispatch(handler, fields, message_id, loop, stream, group)
            for message_id, fields in read_new(stream, group, consumer_name):
                dispatch(handler, fields, message_id, loop, stream, group)
        except Exception:
            log_event(None, group, "consumer_error")
            time.sleep(1)
