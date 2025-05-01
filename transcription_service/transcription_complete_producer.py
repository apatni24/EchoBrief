from redis_stream_client import redis_client, TRANSCRIPTION_COMPLETE_STREAM
import json

def emit_transcription_completed(data: dict):
    redis_client.xadd(TRANSCRIPTION_COMPLETE_STREAM, {"data": json.dumps(data)})
    redis_client.xtrim(TRANSCRIPTION_COMPLETE_STREAM, maxlen="500")
    print(f"✅ Event emitted: transcription_completed for {data['file_path']}")

# Example usage
# if __name__ == "__main__":
#     emit_transcription_completed("audio_files/transcribing_2.mp3")
