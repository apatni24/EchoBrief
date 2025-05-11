import assemblyai as aai
import os
from dotenv import load_dotenv
import requests

load_dotenv()

aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")

# Set up config with diarization
config = aai.TranscriptionConfig(
    speaker_labels=True,
    punctuate=True,
    language_code="en_us"
)

# Create transcriber instance
transcriber = aai.Transcriber(config=config)

def transcribe_audio(file_path: str):
    print("Transcribing...")
    transcript = transcriber.transcribe(file_path, config=config)
    

    final_transcript = []
    print("Transcript:")
    for utterance in transcript.utterances:
        line = f"[Speaker {utterance.speaker}] {utterance.text}"
        final_transcript.append(line)
    return "\n".join(final_transcript)
