import hashlib
import requests
import time
import re

API_KEY = 'QRKETXXMUYM3ZEDVPT9U'
API_SECRET = 'b$HAKs4prEqyNkJvmU4^mhZwDDAQn##LLfyRgvAd'

def get_rss_feed_url(podcast_title):
    url = f"https://api.podcastindex.org/api/1.0/search/bytitle?q={podcast_title}"
    epoch_time = int(time.time())
    data_to_hash = API_KEY + API_SECRET + str(epoch_time)
    sha_1 = hashlib.sha1(data_to_hash.encode()).hexdigest()

    headers = {
        'X-Auth-Date': str(epoch_time),
        'X-Auth-Key': API_KEY,
        'Authorization': sha_1,
        'User-Agent': 'podcasting-index-python-client'
    }

    response = requests.post(url, headers=headers)

    if response.status_code == 200:
        feeds = response.json().get('feeds', [])
        if feeds:
            return feeds[0].get('url')
    return None

def get_rss_from_apple_link(apple_episode_url):
    """
    Extract RSS feed URL from Apple Podcast episode link.
    """
    # Extract Podcast ID (e.g., id1789644662)
    match = re.search(r'/id(\d+)', apple_episode_url)
    if not match:
        print("Invalid Apple Podcast URL format.")
        return None

    podcast_id = match.group(1)
    print(f"Extracted Podcast ID: {podcast_id}")

    # Prepare Podcast Index API call
    url = f"https://api.podcastindex.org/api/1.0/podcasts/byitunesid?id={podcast_id}"

    epoch_time = int(time.time())
    data_to_hash = API_KEY + API_SECRET + str(epoch_time)
    sha_1 = hashlib.sha1(data_to_hash.encode()).hexdigest()

    headers = {
        'X-Auth-Date': str(epoch_time),
        'X-Auth-Key': API_KEY,
        'Authorization': sha_1,
        'User-Agent': 'podcasting-index-python-client'
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        print(response.json())
        feed_data = response.json().get('feed')
        if feed_data:
            rss_url = feed_data.get('url')
            print(f"RSS Feed URL: {rss_url}")
            return rss_url
        else:
            print("No feed data found for this Podcast ID.")
            return None
    else:
        print(f"API Error: {response.status_code}")
        return None