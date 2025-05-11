import os
import re
import time
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv()

ENV = os.getenv("ENV", "dev")
API_KEY = os.getenv("PODCAST_INDEX_API_KEY", "dummy-key" if ENV == "test" else None)
API_SECRET = os.getenv("PODCAST_INDEX_API_SECRET", "dummy-secret" if ENV == "test" else None)

if ENV != "test" and (not API_KEY or not API_SECRET):
    raise RuntimeError("Missing PODCAST_INDEX_API_KEY or PODCAST_INDEX_API_SECRET")

PODCAST_INDEX_BASE_URL = "https://api.podcastindex.org/api/1.0"


def _get_auth_headers():
    epoch_time = int(time.time())
    data_to_hash = API_KEY + API_SECRET + str(epoch_time)
    sha_1 = hashlib.sha1(data_to_hash.encode()).hexdigest()

    return {
        'X-Auth-Date': str(epoch_time),
        'X-Auth-Key': API_KEY,
        'Authorization': sha_1,
        'User-Agent': 'podcasting-index-python-client'
    }


def get_rss_feed_url(podcast_title):
    """
    Search for RSS feed by podcast title using Podcast Index API.
    """
    try:
        url = f"{PODCAST_INDEX_BASE_URL}/search/bytitle?q={podcast_title}"
        response = requests.post(url, headers=_get_auth_headers(), timeout=5)

        if response.status_code == 200:
            feeds = response.json().get('feeds', [])
            if feeds:
                return feeds[0].get('url')
            else:
                print(f"[PodcastIndex] No feeds found for title: {podcast_title}")
        else:
            print(f"[PodcastIndex] HTTP {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[PodcastIndex] Error fetching feed URL: {e}")

    return None


def get_rss_from_apple_link(apple_episode_url):
    """
    Extract RSS feed URL from Apple Podcast episode link using Podcast Index API.
    """
    match = re.search(r'/id(\d+)', apple_episode_url)
    if not match:
        print("[PodcastIndex] Invalid Apple Podcast URL format.")
        return None

    podcast_id = match.group(1)
    print(f"[PodcastIndex] Extracted Podcast ID: {podcast_id}")

    try:
        url = f"{PODCAST_INDEX_BASE_URL}/podcasts/byitunesid?id={podcast_id}"
        response = requests.get(url, headers=_get_auth_headers(), timeout=5)

        if response.status_code == 200:
            feed_data = response.json().get('feed')
            if feed_data:
                rss_url = feed_data.get('url')
                print(f"[PodcastIndex] RSS Feed URL: {rss_url}")
                return rss_url
            else:
                print("[PodcastIndex] No feed data found for this Podcast ID.")
        else:
            print(f"[PodcastIndex] API Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[PodcastIndex] Error fetching RSS from Apple link: {e}")

    return None
