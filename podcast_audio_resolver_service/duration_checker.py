import requests
import os

PODCAST_INDEX_BASE_URL = "https://api.podcastindex.org/api/1.0"
API_KEY = os.getenv("PODCASTINDEX_API_KEY")
API_SECRET = os.getenv("PODCASTINDEX_API_SECRET")

import hashlib
import time
import base64
import hmac

def _get_auth_headers():
    now = int(time.time())
    data_to_sign = f"{API_KEY}{API_SECRET}{now}"
    signature = hmac.new(API_SECRET.encode(), data_to_sign.encode(), hashlib.sha1).hexdigest()

    return {
        "User-Agent": "EchoBrief",
        "X-Auth-Date": str(now),
        "X-Auth-Key": API_KEY,
        "Authorization": signature
    }

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
