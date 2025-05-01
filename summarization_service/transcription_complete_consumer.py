from redis_stream_client import redis_client, TRANSCRIPTION_COMPLETE_STREAM
from summarization_service import summarize
import asyncio
import json
from summarization_service.ws_manager import manager

async def consume_transcription_completed():
    print("🎧 Trimming old stream entries and starting consumer...")
    redis_client.xtrim(TRANSCRIPTION_COMPLETE_STREAM, maxlen=0)
    last_id = "$"  # only listen to *new* messages
    print("Listening for transcription_complete events...")

    try:
        while True:
            messages = redis_client.xread({TRANSCRIPTION_COMPLETE_STREAM: last_id}, block=60000, count=1)
            for stream, entries in messages:
                for msg_id, data in entries:
                    # print(f"🎧 Received: {data}")
                    last_id = msg_id

                    raw_json = data.get('data')
                    if raw_json:
                        try:
                            parsed_data = json.loads(raw_json)
                        except json.JSONDecodeError as e:
                            print("❌ Failed to decode JSON:", e)
                            continue
                    else:
                        continue

                    job_id = parsed_data['job_id']
                    summary_type = parsed_data['summary_type']
                    transcript = parsed_data['transcript']
                    episode_summary = parsed_data['metadata']['summary']
                    show_title = parsed_data['metadata']['show_title']
                    show_summary = parsed_data['metadata']['show_summary']

                    # Summarize transcript using llm
                    try:
                        summary = summarize.get_summary(
                            summary_type,
                            transcript,
                            episode_summary,
                            show_title,
                            show_summary,
                        )
                        print(summary)
                    except Exception as e:
                        print(f"Summarization failed for job {job_id}: {e}")
                        continue
                    await manager.broadcast(job_id, {
                        "job_id": job_id,
                        "status": "done",
                        "summary": summary,
                    })
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        print("🛑 Consumer task cancelled — shutting down gracefully.")
    except Exception as e:
        print("Error in consumer:", e)


if __name__ == "__main__":
    consume_transcription_completed()