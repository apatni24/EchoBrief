"""Evaluate agent/policies.yaml. No caller identity is an input."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from redis_stream_client import redis_client

BUDGET_KEY = "budget:uncached_summarize"
DEFAULT_APPROVAL_TTL = 900


@dataclass
class PolicyDecision:
    effect: str
    policy_id: str | None = None
    error_code: str | None = None
    expires_in_seconds: int | None = None
    message: str | None = None


@lru_cache(maxsize=1)
def load_policies() -> tuple[dict, ...]:
    raw = yaml.safe_load(Path(__file__).with_name("policies.yaml").read_text()) or {}
    return tuple(raw.get("policies") or [])


def budget_max() -> int:
    for policy in load_policies():
        if policy.get("id") == "uncached-summarize-budget":
            return int(policy.get("max_uncached_jobs", 30))
    return 30


def budget_window_seconds() -> int:
    for policy in load_policies():
        if policy.get("id") == "uncached-summarize-budget":
            return int(policy.get("window_seconds", 3600))
    return 3600


def current_uncached_count() -> int:
    raw = redis_client.get(BUDGET_KEY)
    return int(raw or 0)


def increment_uncached_budget() -> int:
    count = int(redis_client.incr(BUDGET_KEY))
    if count == 1:
        redis_client.expire(BUDGET_KEY, budget_window_seconds())
    return count


def _duration_threshold(policy: dict) -> int:
    match = re.search(r"duration_seconds\s*>\s*(\d+)", str(policy.get("when", "")))
    if match:
        return int(match.group(1))
    return 1800


def evaluate(operation: str, *, episode_cache_hit: bool = False,
             duration_seconds: int | None = None,
             uncached_count: int | None = None,
             skip_budget: bool = False) -> PolicyDecision:
    for policy in load_policies():
        if policy.get("operation") != operation:
            continue
        policy_id = policy.get("id")
        if policy_id == "episode-duration-cap":
            if duration_seconds is None:
                continue
            try:
                duration = int(duration_seconds)
            except (TypeError, ValueError):
                continue
            if duration > _duration_threshold(policy):
                return PolicyDecision(
                    effect="deny",
                    policy_id=policy_id,
                    error_code=policy.get("error_code") or "episode_too_long",
                    message="Episodes longer than 30 minutes are not supported.",
                )
            continue
        if policy_id == "uncached-summarize-budget":
            if skip_budget or episode_cache_hit or policy.get("when") != "episode_cache_miss":
                continue
            count = current_uncached_count() if uncached_count is None else int(uncached_count)
            if count >= budget_max():
                return PolicyDecision(
                    effect="pending",
                    policy_id=policy_id,
                    error_code="approval_required",
                    expires_in_seconds=int(policy.get("expires_in_seconds") or DEFAULT_APPROVAL_TTL),
                    message="The global uncached-summarize budget is exhausted.",
                )
            continue
        if policy.get("effect") == "require_approval":
            return PolicyDecision(
                effect="pending",
                policy_id=policy_id,
                error_code="approval_required",
                expires_in_seconds=int(policy.get("expires_in_seconds") or DEFAULT_APPROVAL_TTL),
            )
    return PolicyDecision(effect="allow")
