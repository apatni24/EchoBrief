# summarization_service/transcription_complete_consumer.py
from redis_stream_client import redis_client, TRANSCRIPTION_COMPLETE_STREAM
from summarization_service import summarize
from summarization_service.ws_manager import manager
from cache_service import CacheService
import json, asyncio

def consume_transcription_completed(loop):
    print("🎧 Starting consumer…")
    redis_client.xtrim(TRANSCRIPTION_COMPLETE_STREAM, maxlen=0)
    last_id = "0"

    try:
        while True:
            messages = redis_client.xread(
                {TRANSCRIPTION_COMPLETE_STREAM: last_id},
                block=60000, count=1
            )
            for _, entries in messages:
                for msg_id, data in entries:
                    last_id = msg_id
                    raw = data.get("data")
                    if not raw:
                        continue
                    if isinstance(raw, bytes):
                        raw = raw.decode()
                    parsed = json.loads(raw)

                    # do your summarization… 
                    summary = summarize.get_summary(
                        parsed["summary_type"],
                        parsed["transcript"],
                        parsed["metadata"]["summary"],
                        parsed["metadata"]["show_title"],
                        parsed["metadata"]["show_summary"],
                    )

                    # Cache the episode result
                    if "platform" in parsed and "episode_id" in parsed:
                        episode_data = {
                            "summary": summary,
                            "metadata": parsed["metadata"],
                            "summary_type": parsed["summary_type"],
                            "transcript_length": len(parsed["transcript"]),
                            "processing_time": parsed.get("processing_time", 0),
                            "file_path": parsed.get("file_path", "")
                        }
                        
                        CacheService.set_cached_episode(
                            parsed["platform"],
                            parsed["episode_id"],
                            parsed["summary_type"],
                            episode_data
                        )

                    payload = {
                        "job_id": parsed["job_id"],
                        "status": "done",
                        "summary": summary,
                    }

                    # schedule the async broadcast on the main loop
                    loop.call_soon_threadsafe(
                        asyncio.create_task,
                        manager.broadcast(parsed["job_id"], payload)
                    )


    except Exception as e:
        print("Consumer error:", e)

if __name__ == "__main__":
    consume_transcription_completed()