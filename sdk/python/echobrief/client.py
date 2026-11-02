from __future__ import annotations

import os
import time
from typing import Any

import httpx

DEFAULT_BASE = "https://echobrief-backend.onrender.com"


class EchoBriefClient:
    def __init__(self, base_url: str | None = None, timeout: float = 60.0):
        self.base_url = (base_url or os.getenv("ECHOBRIEF_BASE_URL") or DEFAULT_BASE).rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "EchoBriefClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        response = self._client.request(method, path, **kwargs)
        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text}
        return {"ok": response.is_success, "status": response.status_code, "data": data}

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def capabilities(self) -> dict[str, Any]:
        return self._request("GET", "/.well-known/echobrief/capabilities.json")

    def sandbox(self) -> dict[str, Any]:
        return self._request("GET", "/agent/v1/sandbox")

    def summarize(
        self,
        url: str,
        summary_type: str = "ts",
        *,
        idempotency_key: str | None = None,
        cache_only: bool = False,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if cache_only:
            headers["X-EchoBrief-Cache-Only"] = "true"
        params = {"cache_only": "true"} if cache_only else None
        body: dict[str, Any] = {"url": url, "summary_type": summary_type}
        if cache_only:
            body["cache_only"] = True
        return self._request(
            "POST",
            "/agent/v1/episodes/summaries",
            json=body,
            headers=headers,
            params=params,
        )

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/agent/v1/jobs/{job_id}")

    def get_summary(self, platform: str, episode_id: str, summary_type: str) -> dict[str, Any]:
        return self._request(
            "GET",
            "/agent/v1/summaries",
            params={
                "platform": platform,
                "episode_id": episode_id,
                "summary_type": summary_type,
            },
        )

    def wait_for_job(
        self,
        job_id: str,
        *,
        interval_seconds: float = 2.0,
        timeout_seconds: float = 240.0,
    ) -> dict[str, Any]:
        started = time.time()
        while time.time() - started < timeout_seconds:
            result = self.get_job(job_id)
            status = (result.get("data") or {}).get("status")
            if status in {"done", "failed", "cancelled", "expired"}:
                return result
            time.sleep(interval_seconds)
        raise TimeoutError(f"Timed out waiting for job {job_id}")
