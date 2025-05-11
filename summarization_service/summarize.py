import os
import time
import requests
from dotenv import load_dotenv
from summarization_service.summary_types import (
    bullet_points_summary as bps,
    narrative_summary as ns,
    takeaway_summary as ts
)

load_dotenv()

ENV = os.getenv("ENV", "dev")

# Load environment variables
CHATGROQ_API_KEY = os.getenv("CHATGROQ_API_KEY", "dummy-key" if ENV == "test" else None)
CHATGROQ_API_URL = os.getenv("CHATGROQ_API_URL", "https://api.fakeurl.com/v1" if ENV == "test" else None)
MODEL_NAME = os.getenv("MODEL_NAME", "llama-3.3-70b-versatile")
RANDOM_STRING = os.getenv("RANDOM_STRING", "default")

# Fail fast if real keys are missing in non-test env
if ENV != "test" and (not CHATGROQ_API_KEY or not CHATGROQ_API_URL):
    raise RuntimeError("Missing CHATGROQ_API_KEY or CHATGROQ_API_URL in environment variables.")

# Rate limiting: ensure at least 60 seconds between calls
t_last_request_time = 0.0

def _rate_limit():
    global t_last_request_time
    now = time.time()
    elapsed = now - t_last_request_time
    if elapsed < 60:
        wait = 60 - elapsed
        print(f"[Summarizer] Rate limit in effect, sleeping for {wait:.1f}s...")
        time.sleep(wait)
    t_last_request_time = time.time()

def get_summary(summary_type: str, transcript: str, episode_summary: str, show_title: str, show_summary: str) -> str:
    print("[Summarizer] Generating summary...")

    _rate_limit()

    try:
        # Select prompt and system message
        if summary_type == 'ts':
            prompt = ts.get_prompt(transcript, episode_summary, show_title, show_summary)
            system_message = ts.get_system_message()
        elif summary_type == 'ns':
            prompt = ns.get_prompt(transcript, episode_summary, show_title, show_summary)
            system_message = ns.get_system_message()
        else:
            prompt = bps.get_prompt(transcript, episode_summary, show_title, show_summary)
            system_message = bps.get_system_message()

        payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_completion_tokens": 16384
        }

        headers = {
            "Authorization": f"Bearer {CHATGROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        response = requests.post(CHATGROQ_API_URL, headers=headers, json=payload)
        response.raise_for_status()

        result = response.json()
        choices = result.get("choices", [])

        if choices:
            return choices[0].get("message", {}).get("content", "No content in response.")
        else:
            return "No response generated."

    except requests.exceptions.RequestException as e:
        print(f"[Summarizer] HTTP error: {e}")
        return "Error: HTTP request failed."
    except Exception as e:
        print(f"[Summarizer] Unexpected error: {e}")
        return "Error: Could not generate summary."
