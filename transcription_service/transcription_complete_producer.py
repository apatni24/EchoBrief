from redis_stream_client import (
    SUMMARIZATION_GROUP,
    TRANSCRIPTION_COMPLETE_STREAM,
    redis_client,
    trim_acked_history,
)
from agent.audit import append as audit_append
import json

def emit_transcription_completed(data: dict):
    try:
        stream_id = redis_client.xadd(TRANSCRIPTION_COMPLETE_STREAM, {"data": json.dumps(data)})
    except Exception as err:
        print("Unable to post message:", err)
        raise
    trim_acked_history(TRANSCRIPTION_COMPLETE_STREAM, SUMMARIZATION_GROUP)
    job_id = data.get("job_id") if isinstance(data, dict) else None
    try:
        audit_append(job_id, "transcribing", "published")
    except Exception:
        pass
    return stream_id
