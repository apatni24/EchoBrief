import os
import time
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv()

ENV = os.getenv("ENV", "dev")  # 'test', 'dev', 'prod'

# Load API credentials
if ENV == "test":
    API_KEY = "dummy-key"
    API_SECRET = "dummy-secret"
else:
    API_KEY = os.getenv("PODCAST_INDEX_API_KEY")
    API_SECRET = os.getenv("PODCAST_INDEX_API_SECRET")

    if not API_KEY or not API_SECRET:
        raise RuntimeError("Missing Podcast Index API credentials in environment variables.")

PODCAST_INDEX_BASE_URL = "https://api.podcastindex.org/api/1.0"

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

def get_duration_from_episode(episode):
    return episode.get("duration", 0)
