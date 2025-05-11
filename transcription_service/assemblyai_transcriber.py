import os
import assemblyai as aai
from dotenv import load_dotenv

load_dotenv()

# Determine environment
ENV = os.getenv("ENV", "dev")  # 'test', 'dev', 'prod', etc.

# Get API key with fallback in test env
API_KEY = os.getenv("ASSEMBLYAI_API_KEY", "dummy-key" if ENV == "test" else None)

if not API_KEY:
    raise RuntimeError("Missing required ASSEMBLYAI_API_KEY environment variable")

# Configure AssemblyAI
aai.settings.api_key = API_KEY

config = aai.TranscriptionConfig(
    speaker_labels=True,
    punctuate=True,
    language_code="en_us"
)

transcriber = aai.Transcriber(config=config)

def transcribe_audio(file_path: str):
    print("Transcribing...")
    try:
        transcript = transcriber.transcribe(file_path, config=config)
    except Exception as e:
        print(f"Transcription failed: {e}")
        raise

    final_transcript = []
    print("Transcript:")
    for utterance in transcript.utterances:
        line = f"[Speaker {utterance.speaker}] {utterance.text}"
        final_transcript.append(line)

    return "\n".join(final_transcript)
