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

                    try:
                        # Extract episode title from metadata
                        episode_title = None
                        duration = None
                        if "metadata" in parsed and parsed["metadata"]:
                            episode_title = parsed["metadata"].get("episode_title")
                            duration = parsed["metadata"].get("duration")
                        
                        # Check transcript-level cache first
                        cached_transcript = CacheService.get_cached_transcript(parsed["transcript"])
                        if cached_transcript:
                            # Use cached transcript data - generate summary for the requested type
                            print(f"🎯 Using cached transcript data for {parsed['summary_type']}")
                            # Check if we already have this summary type cached
                            if "summaries" in cached_transcript and parsed["summary_type"] in cached_transcript["summaries"]:
                                summary = cached_transcript["summaries"][parsed["summary_type"]]
                                print(f"🎯 Found cached summary for {parsed['summary_type']}")
                            else:
                                # Generate new summary for this type
                                summary = summarize.get_summary(
                                    parsed["summary_type"],
                                    parsed["transcript"],
                                    parsed["metadata"]["summary"],
                                    parsed["metadata"]["show_title"],
                                    parsed["metadata"]["show_summary"],
                                    episode_title,
                                    duration
                                )
                                # Update the cached transcript with the new summary type
                                if "summaries" not in cached_transcript:
                                    cached_transcript["summaries"] = {}
                                cached_transcript["summaries"][parsed["summary_type"]] = summary
                                # Update the cache with the new summary
                                CacheService.set_cached_transcript(
                                    parsed["transcript"],
                                    cached_transcript
                                )
                        else:
                            # Generate new summary
                            summary = summarize.get_summary(
                                parsed["summary_type"],
                                parsed["transcript"],
                                parsed["metadata"]["summary"],
                                parsed["metadata"]["show_title"],
                                parsed["metadata"]["show_summary"],
                                episode_title,
                                duration
                            )
                            # Cache the transcript data with the first summary
                            transcript_data = {
                                "transcript": parsed["transcript"],
                                "metadata": parsed["metadata"],
                                "transcript_length": len(parsed["transcript"]),
                                "processing_time": parsed.get("processing_time", 0),
                                "file_path": parsed.get("file_path", ""),
                                "summaries": {
                                    parsed["summary_type"]: summary
                                }
                            }
                            CacheService.set_cached_transcript(
                                parsed["transcript"],
                                transcript_data
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
                    except Exception as err:
                        print("[Error] Failed to generate or cache summary:", err)
                        payload = {
                            "job_id": parsed.get("job_id", None),
                            "status": "error",
                            "error": str(err)
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