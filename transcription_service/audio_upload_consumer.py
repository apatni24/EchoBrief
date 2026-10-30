from redis_stream_client import AUDIO_UPLOADED_STREAM, TRANSCRIPTION_GROUP, ensure_consumer_group
from transcription_service import assemblyai_transcriber, transcription_complete_producer
from cache_service import CacheService
from agent import jobs
from agent.audit import log_event
from agent.delivery import ack, consume_loop, fail_stage
from agent.errors import is_transient_exception
import asyncio
import hashlib
import json
import os


def prepare_audio_consumer():
    """Create the transcription group at $ without deleting queued work."""
    ensure_consumer_group(AUDIO_UPLOADED_STREAM, TRANSCRIPTION_GROUP)


def _entry(parsed_data: dict) -> dict:
    return {key: value for key, value in parsed_data.items() if key != "transcript"}


async def _handle_message(parsed_data, message_id=None):
    job_id = parsed_data.get("job_id")
    job = jobs.get_job(job_id) if job_id else None
    if job and (jobs.is_terminal(job) or job.get("status") in {"summarizing", "done"}):
        ack(AUDIO_UPLOADED_STREAM, TRANSCRIPTION_GROUP, message_id)
        return
    if job and jobs.is_past(job.get("deadline_at")):
        jobs.fail_job(job_id, "timeout", retryable=True)
        ack(AUDIO_UPLOADED_STREAM, TRANSCRIPTION_GROUP, message_id)
        return
    if job and job.get("status") in {"accepted", "resolving", "transcribing"}:
        if job.get("status") != "transcribing":
            jobs.transition(job_id, "transcribing")

    file_path = parsed_data["file_path"]
    if not os.path.exists(file_path):
        log_event(job_id, "transcribing", "audio_missing")
        fail_stage(
            job_id=job_id,
            stage="transcribing",
            code="audio_missing",
            message="Audio file not found.",
            retryable=False,
            stream=AUDIO_UPLOADED_STREAM,
            group=TRANSCRIPTION_GROUP,
            message_id=message_id,
            entry=_entry(parsed_data),
        )
        return

    try:
        if parsed_data.get("file_hash"):
            file_hash = parsed_data["file_hash"]
        else:
            with open(file_path, "rb") as handle:
                file_hash = hashlib.md5(handle.read()).hexdigest()

        cached_transcript = CacheService.get_cached_transcript_by_hash(file_hash)
        if cached_transcript:
            message_txt = cached_transcript["transcript"]
            cache_flags = {"file": True, "transcript": True}
        else:
            message_txt = await asyncio.to_thread(assemblyai_transcriber.transcribe_audio, file_path)
            transcript_data = {
                "transcript": message_txt,
                "metadata": parsed_data.get("metadata", {}),
                "transcript_length": len(message_txt),
                "processing_time": 0,
                "file_path": file_path,
                "file_hash": file_hash,
                "summaries": {},
            }
            CacheService.set_cached_transcript_by_hash(file_hash, transcript_data)
            cache_flags = {"file": True, "transcript": False}

        content_hash = hashlib.sha256(message_txt.encode("utf-8")).hexdigest()
        if job_id:
            jobs.remember_transcript(
                job_id,
                file_hash=file_hash,
                transcript_hash=content_hash,
                transcript_length=len(message_txt),
                cache_flags=cache_flags,
                file_path=file_path,
                metadata=parsed_data.get("metadata"),
            )
            fresh = jobs.get_job(job_id)
            if fresh and jobs.is_terminal(fresh):
                ack(AUDIO_UPLOADED_STREAM, TRANSCRIPTION_GROUP, message_id)
                return

        parsed_data["transcript"] = message_txt
        parsed_data["file_hash"] = file_hash
        transcription_complete_producer.emit_transcription_completed(parsed_data)
        ack(AUDIO_UPLOADED_STREAM, TRANSCRIPTION_GROUP, message_id)
        log_event(job_id, "transcribing", "completed")
    except Exception as exc:
        retryable = is_transient_exception(exc)
        fail_stage(
            job_id=job_id,
            stage="transcribing",
            code="upstream_unavailable",
            message="Transcription failed.",
            retryable=retryable,
            stream=AUDIO_UPLOADED_STREAM,
            group=TRANSCRIPTION_GROUP,
            message_id=message_id,
            entry=_entry(parsed_data),
        )


def consume_audio_uploaded(loop):
    log_event(None, "transcribing", "consumer_started")
    consume_loop(
        AUDIO_UPLOADED_STREAM,
        TRANSCRIPTION_GROUP,
        "transcription",
        _handle_message,
        loop,
    )
