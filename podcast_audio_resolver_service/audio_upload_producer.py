from redis_stream_client import (
    AUDIO_UPLOADED_STREAM,
    TRANSCRIPTION_GROUP,
    redis_client,
    trim_acked_history,
)
from agent.audit import append as audit_append
import json

def emit_audio_uploaded(data: dict):
    try:
        stream_id = redis_client.xadd(AUDIO_UPLOADED_STREAM, {"data": json.dumps(data)})
    except Exception as err:
        print("Unable to post message:", err)
        raise
    trim_acked_history(AUDIO_UPLOADED_STREAM, TRANSCRIPTION_GROUP)
    job_id = data.get("job_id") if isinstance(data, dict) else None
    try:
        audit_append(job_id, "resolving", "published")
    except Exception:
        pass
    return stream_id

# Example usage
if __name__ == "__main__":
    emit_audio_uploaded({'file_path': 'audio_files/The_Bearcat_Tip-Off_Talk,_Ep._90,_West_Virginia.mp3', 'metadata': {'summary': "<p>J.T. Smith, Neil Meyer and Alex Meacham recap\xa0Utah loss, preview West Virginia, highlight the players to watch, who would you want to have dinner with (Burrow, De La Cruz or the Kelce's), have you tried Skyline ice cream and more.</p>", 'show_title': 'TFON', 'show_summary': 'The Front Office News covers the University of Cincinnati athletics. Our podcast will be a quick hitting pod talking about the Bearcats\nhttp://thefrontofficenews.com'}})
