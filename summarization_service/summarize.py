import os
import time
import requests
from dotenv import load_dotenv
from summarization_service.summary_types import bullet_points_summary as bps, narrative_summary as ns, takeaway_summary as ts

load_dotenv()

CHATGROQ_API_KEY = os.getenv("CHATGROQ_API_KEY")
CHATGROQ_API_URL = os.getenv("CHATGROQ_API_URL")
MODEL_NAME = "llama-3.3-70b-versatile"
RANDOM_STRING = os.getenv("RANDOM_STRING")

# Rate limiting: ensure at least 60 seconds between external API calls
t_last_request_time = 0.0

def get_summary(summary_type: str, transcript: str, episode_summary: str, show_title: str, show_summary: str) -> str:
    global t_last_request_time
    print("generating summary...")

    # Enforce 60-second interval between requests
    now = time.time()
    elapsed = now - t_last_request_time
    if elapsed < 60:
        wait = 60 - elapsed
        print(f"Rate limit in effect, waiting {wait:.1f} seconds before calling API...")
        time.sleep(wait)

    try:
        # Build prompt and system message based on desired style
        if summary_type == 'ts':
            prompt = ts.get_prompt(
                transcript=transcript,
                summary=episode_summary,
                show_title=show_title,
                show_summary=show_summary,
            )
            system_message = ts.get_system_message()
        elif summary_type == 'ns':
            prompt = ns.get_prompt(
                transcript=transcript,
                summary=episode_summary,
                show_title=show_title,
                show_summary=show_summary,
            )
            system_message = ns.get_system_message()
        else:
            prompt = bps.get_prompt(
                transcript=transcript,
                summary=episode_summary,
                show_title=show_title,
                show_summary=show_summary,
            )
            system_message = bps.get_system_message()

        headers = {
            "Authorization": f"Bearer {CHATGROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_completion_tokens": 16384
        }

        # Perform the API call
        response = requests.post(CHATGROQ_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()

        # Record this call time for rate limiting
        t_last_request_time = time.time()

        # Extract and return the generated text
        choices = result.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "No response generated.")
        else:
            return "No response generated."

    except Exception as e:
        print(f"Error during summarization: {e}")
        return "Error: Could not generate summary."
