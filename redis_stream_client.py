import os
import time

import redis
from dotenv import load_dotenv

load_dotenv()

ENV = os.getenv("ENV", "dev")  # default to dev

# Provide dummy values during tests
if ENV == "test":
    upstash_redis_host = "localhost"
    upstash_redis_port = 6379
    upstash_redis_password = None
else:
    upstash_redis_host = os.getenv("UPSTASH_REDIS_HOST")
    upstash_redis_port = int(os.getenv("UPSTASH_REDIS_PORT", "0"))  # convert to int
    upstash_redis_password = os.getenv("UPSTASH_REDIS_PASSWORD")

    # Fail fast if any required config is missing
    if not all([upstash_redis_host, upstash_redis_port, upstash_redis_password]):
        raise RuntimeError("Missing required Upstash Redis environment variables")

# Create the Redis client
redis_client = redis.Redis(
    host=upstash_redis_host,
    port=upstash_redis_port,
    password=upstash_redis_password,
    ssl=(ENV != "test"),            # TLS only for non-test envs
    decode_responses=True
)

# Stream names
AUDIO_UPLOADED_STREAM = "audio_uploaded"
TRANSCRIPTION_COMPLETE_STREAM = "transcription_complete"
JOBS_DLQ_STREAM = "jobs_dlq"

# One group per existing process. Created at "$" so a deploy does not replay history.
TRANSCRIPTION_GROUP = "transcription"
SUMMARIZATION_GROUP = "summarization"


def ensure_consumer_group(stream: str, group: str) -> None:
    try:
        redis_client.xgroup_create(name=stream, groupname=group, id="$", mkstream=True)
    except redis.exceptions.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def read_group(stream: str, group: str, consumer: str, count: int = 1, block_ms: int = 5000):
    return redis_client.xreadgroup(group, consumer, {stream: ">"}, count=count, block=block_ms)


def ack(stream: str, group: str, message_id: str):
    return redis_client.xack(stream, group, message_id)


def autoclaim(stream: str, group: str, consumer: str, min_idle_ms: int = 15000, count: int = 10):
    return redis_client.xautoclaim(stream, group, consumer, min_idle_ms, "0-0", count=count)


def group_exists(stream: str, group: str) -> bool:
    try:
        groups = redis_client.xinfo_groups(stream)
    except Exception:
        return False
    for item in groups or []:
        name = item.get("name") if isinstance(item, dict) else None
        if name == group:
            return True
    return False


def _stream_id_tuple(value: str):
    millis, seq = str(value).split("-", 1)
    return int(millis), int(seq)


def trim_acked_history(stream: str, group: str) -> None:
    """Drop acknowledged entries older than a day. Never trim at or before a pending id."""
    try:
        summary = redis_client.xpending(stream, group)
    except Exception:
        return
    pending = 0
    pending_min = None
    if isinstance(summary, dict):
        pending = int(summary.get("pending") or 0)
        pending_min = summary.get("min")
    elif isinstance(summary, (list, tuple)) and summary:
        pending = int(summary[0] or 0)
        if len(summary) > 1:
            pending_min = summary[1]
    cutoff = f"{int(time.time() * 1000) - 86_400_000}-0"
    minid = cutoff
    if pending and pending_min:
        try:
            if _stream_id_tuple(pending_min) < _stream_id_tuple(cutoff):
                minid = str(pending_min)
        except (TypeError, ValueError):
            minid = str(pending_min)
    try:
        redis_client.xtrim(stream, minid=minid, approximate=False)
    except Exception:
        return
