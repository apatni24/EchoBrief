"""Optional job.completed webhook. Unset URL means nobody is listening."""

from __future__ import annotations

import os

import requests

from agent.audit import log_event

WEBHOOK_ENV = "ECHOBRIEF_WEBHOOK_URL"


def notify_completed(job: dict) -> None:
    url = (os.getenv(WEBHOOK_ENV) or "").strip()
    if not url or job.get("status") != "done":
        return
    body = {
        "event": "job.completed",
        "job_id": job.get("job_id"),
        "operation": job.get("operation"),
        "status": job.get("status"),
    }
    try:
        requests.post(url, json=body, timeout=3)
    except Exception:
        log_event(job.get("job_id"), job.get("status") or "done", "webhook_failed")
