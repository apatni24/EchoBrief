import requests
import os
from dotenv import load_dotenv

load_dotenv()

PODCAST_INDEX_BASE_URL = "https://api.podcastindex.org/api/1.0"
API_KEY = os.getenv("PODCAST_INDEX_API_KEY")
API_SECRET = os.getenv("PODCAST_INDEX_API_SECRET")

import hashlib
import time
import base64
import hmac

def _get_auth_headers():
    epoch_time = int(time.time())
    data_to_hash = API_KEY + API_SECRET + str(epoch_time)
    sha_1 = hashlib.sha1(data_to_hash.encode()).hexdigest()

    headers = {
        'X-Auth-Date': str(epoch_time),
        'X-Auth-Key': API_KEY,
        'Authorization': sha_1,
        'User-Agent': 'podcasting-index-python-client'
    }
    return headers

def get_duration_from_title(feed_url, episode_title):
    try:
        response = requests.get(
            f"{PODCAST_INDEX_BASE_URL}/episodes/byfeedurl",
            params={"url": feed_url},
            headers=_get_auth_headers(),
            timeout=5
        )
        response.raise_for_status()
        episodes = response.json().get("items", [])

        for ep in episodes:
            if episode_title.lower() in ep.get("title", "").lower():
                return ep.get("duration", 0)  # in seconds

    except Exception as e:
        print(f"Error fetching duration: {e}")

    return None
