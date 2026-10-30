# summarization_service/transcription_complete_consumer.py
from redis_stream_client import SUMMARIZATION_GROUP, TRANSCRIPTION_COMPLETE_STREAM, ensure_consumer_group
from summarization_service import summarize
from summarization_service.ws_manager import manager
from cache_service import CacheService
from agent import jobs
from agent.audit import log_event
from agent.delivery import ack, consume_loop, fail_stage
from agent.errors import is_transient_exception
import asyncio
import hashlib
import json
import math
from datetime import datetime, timezone


def prepare_summary_consumer():
    ensure_consumer_group(TRANSCRIPTION_COMPLETE_STREAM, SUMMARIZATION_GROUP)


def _broadcast(loop, job_id, payload):
    if not job_id or loop is None:
        return
    loop.call_soon_threadsafe(asyncio.create_task, manager.broadcast(job_id, payload))


def _metadata_subset(metadata):
    if not isinstance(metadata, dict):
        return {}
    kept = ("episode_title", "show_title", "show_summary", "image_url", "duration", "summary")
    return {key: metadata.get(key) for key in kept if key in metadata}


def _seconds_left(job) -> float | None:
    deadline = job.get("deadline_at") if job else None
    if not deadline:
        return None
    return (datetime.fromisoformat(deadline) - datetime.now(timezone.utc)).total_seconds()


def handle_transcription_complete(parsed, message_id=None, loop=None):
    job_id = parsed.get("job_id")
    job = jobs.get_job(job_id) if job_id else None
    if job and (job.get("result") or {}).get("summary"):
        payload = {
            "job_id": job_id,
            "status": "done",
            "summary": job["result"]["summary"],
            "cached_at": job["result"].get("cached_at"),
        }
        _broadcast(loop, job_id, payload)
        ack(TRANSCRIPTION_COMPLETE_STREAM, SUMMARIZATION_GROUP, message_id)
        return
    if job and jobs.is_terminal(job):
        ack(TRANSCRIPTION_COMPLETE_STREAM, SUMMARIZATION_GROUP, message_id)
        return
    if job and jobs.is_past(job.get("deadline_at")):
        jobs.fail_job(job_id, "timeout", retryable=True)
        _broadcast(loop, job_id, {"job_id": job_id, "status": "error", "error": "The job exceeded its deadline."})
        ack(TRANSCRIPTION_COMPLETE_STREAM, SUMMARIZATION_GROUP, message_id)
        return
    if job and job.get("status") != "summarizing":
        jobs.transition(job_id, "summarizing")

    ack_payload = {
        "job_id": job_id,
        "status": "summarization_received",
        "message": "Received for summarization. Generating summary...",
    }
    _broadcast(loop, job_id, ack_payload)

    try:
        episode_title = None
        duration = None
        if parsed.get("metadata"):
            episode_title = parsed["metadata"].get("episode_title")
            duration = parsed["metadata"].get("duration")

        cached_transcript = CacheService.get_cached_transcript(parsed["transcript"])
        needs_llm = True
        summary = None
        if cached_transcript and parsed["summary_type"] in (cached_transcript.get("summaries") or {}):
            summary = cached_transcript["summaries"][parsed["summary_type"]]
            needs_llm = False

        if needs_llm and job_id:
            wait = summarize.cooldown_remaining()
            remaining = _seconds_left(jobs.get_job(job_id))
            if wait > 0 and remaining is not None and wait > remaining:
                jobs.set_error_hint(
                    job_id,
                    "rate_limited",
                    retryable=True,
                    retry_after_seconds=int(math.ceil(wait)),
                )
                return

        if summary is None and cached_transcript:
            summary = summarize.get_summary(
                parsed["summary_type"],
                parsed["transcript"],
                parsed["metadata"]["summary"],
                parsed["metadata"]["show_title"],
                parsed["metadata"]["show_summary"],
                episode_title,
                duration,
            )
            if "summaries" not in cached_transcript:
                cached_transcript["summaries"] = {}
            cached_transcript["summaries"][parsed["summary_type"]] = summary
            CacheService.set_cached_transcript(parsed["transcript"], cached_transcript)
        elif summary is None:
            summary = summarize.get_summary(
                parsed["summary_type"],
                parsed["transcript"],
                parsed["metadata"]["summary"],
                parsed["metadata"]["show_title"],
                parsed["metadata"]["show_summary"],
                episode_title,
                duration,
            )
            transcript_data = {
                "transcript": parsed["transcript"],
                "metadata": parsed["metadata"],
                "transcript_length": len(parsed["transcript"]),
                "processing_time": parsed.get("processing_time", 0),
                "file_path": parsed.get("file_path", ""),
                "summaries": {parsed["summary_type"]: summary},
            }
            CacheService.set_cached_transcript(parsed["transcript"], transcript_data)

        cached_at = None
        if parsed.get("platform") and parsed.get("episode_id"):
            episode_data = {
                "summary": summary,
                "metadata": parsed["metadata"],
                "summary_type": parsed["summary_type"],
                "transcript_length": len(parsed["transcript"]),
                "processing_time": parsed.get("processing_time", 0),
                "file_path": parsed.get("file_path", ""),
            }
            CacheService.set_cached_episode(
                parsed["platform"],
                parsed["episode_id"],
                parsed["summary_type"],
                episode_data,
            )
            cached_episode = CacheService.get_cached_episode(
                parsed["platform"],
                parsed["episode_id"],
                parsed["summary_type"],
            )
            if cached_episode and "cached_at" in cached_episode:
                cached_at = cached_episode["cached_at"]

        content_hash = hashlib.sha256(parsed["transcript"].encode("utf-8")).hexdigest()
        if job_id:
            jobs.remember_transcript(
                job_id,
                file_hash=parsed.get("file_hash"),
                transcript_hash=content_hash,
                transcript_length=len(parsed["transcript"]),
                cache_flags={"transcript": cached_transcript is not None, "episode": cached_at is not None},
                file_path=parsed.get("file_path"),
                metadata=_metadata_subset(parsed.get("metadata")),
            )
            completed = jobs.complete_job(job_id, {
                "summary": summary,
                "metadata": _metadata_subset(parsed.get("metadata")),
                "cached": False,
                "cached_at": cached_at,
                "transcript_length": len(parsed["transcript"]),
            })
            if completed is None:
                _broadcast(loop, job_id, {
                    "job_id": job_id,
                    "status": "error",
                    "error": "The job exceeded its deadline.",
                })
                ack(TRANSCRIPTION_COMPLETE_STREAM, SUMMARIZATION_GROUP, message_id)
                return

        payload = {
            "job_id": job_id,
            "status": "done",
            "summary": summary,
            "cached_at": cached_at,
        }
        _broadcast(loop, job_id, payload)
        ack(TRANSCRIPTION_COMPLETE_STREAM, SUMMARIZATION_GROUP, message_id)
        log_event(job_id, "summarizing", "completed")
    except Exception as err:
        print(json.dumps({"job_id": job_id, "stage": "summarizing", "event": "failed"}))
        outcome = fail_stage(
            job_id=job_id,
            stage="summarizing",
            code="upstream_unavailable",
            message="Summarization failed.",
            retryable=is_transient_exception(err),
            stream=TRANSCRIPTION_COMPLETE_STREAM,
            group=SUMMARIZATION_GROUP,
            message_id=message_id,
            entry={key: value for key, value in parsed.items() if key != "transcript"},
        )
        if outcome == "acked":
            _broadcast(loop, job_id, {
                "job_id": job_id,
                "status": "error",
                "error": str(err),
            })


def consume_transcription_completed(loop):
    log_event(None, "summarizing", "consumer_started")
    consume_loop(
        TRANSCRIPTION_COMPLETE_STREAM,
        SUMMARIZATION_GROUP,
        "summarization",
        handle_transcription_complete,
        loop,
    )


if __name__ == "__main__":
    consume_transcription_completed(None)
