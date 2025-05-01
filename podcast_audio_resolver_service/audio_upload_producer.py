from redis_stream_client import redis_client, AUDIO_UPLOADED_STREAM
import json

def emit_audio_uploaded(data: dict):
    try:
        redis_client.xadd(AUDIO_UPLOADED_STREAM, {"data": json.dumps(data)})
        redis_client.xtrim(AUDIO_UPLOADED_STREAM, maxlen="500")
        print(f"✅ Event emitted: audio_uploaded for {data['file_path']}")
    except Exception as err:
        print("Unable to post message:", err)

# Example usage
if __name__ == "__main__":
    emit_audio_uploaded({'file_path': 'audio_files/The_Bearcat_Tip-Off_Talk,_Ep._90,_West_Virginia.mp3', 'metadata': {'summary': "<p>J.T. Smith, Neil Meyer and Alex Meacham recap\xa0Utah loss, preview West Virginia, highlight the players to watch, who would you want to have dinner with (Burrow, De La Cruz or the Kelce's), have you tried Skyline ice cream and more.</p>", 'show_title': 'TFON', 'show_summary': 'The Front Office News covers the University of Cincinnati athletics. Our podcast will be a quick hitting pod talking about the Bearcats\nhttp://thefrontofficenews.com'}})
