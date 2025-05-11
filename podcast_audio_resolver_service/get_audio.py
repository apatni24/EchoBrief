from podcast_audio_resolver_service.spotify_scraper import get_show_and_episode_title
from podcast_audio_resolver_service import apple_scraper
from podcast_audio_resolver_service.rss_fetcher import get_rss_feed_url, get_rss_from_apple_link
from podcast_audio_resolver_service.audio_extractor import download_audio_and_get_metadata
from podcast_audio_resolver_service.duration_checker import get_duration_from_title

import re

def get_episode_audio_from_spotify(episode_url):
    print("Fetching episode and show titles...")
    titles = get_show_and_episode_title(episode_url)

    titles = [title.rstrip() for title in titles]

    print(f"Podcast: \"{titles[1]}\", Episode: \"{titles[0]}\"")

    print("Fetching RSS feed...")
    rss_url = get_rss_feed_url(titles[1])

    if not rss_url:
        print("RSS feed not found.")
        return {
            "error": "RSS feed not found."
        }
    
        # Check episode duration
    duration = get_duration_from_title(rss_url, titles[0])
    print(f"Duration of {titles[0]}: {duration}")
    if duration and duration > 1800:
        return {
            "error": "Episode is longer than 30 minutes. Only shorter episodes are supported currently."
        }


    print("Extracting audio URL...")
    data = download_audio_and_get_metadata(rss_url, titles[0])

    if data:
        print(f"Audio File URL: {data['file_path']}")
        return data
    else:
        print("Failed to retrieve audio URL.")

def get_episode_audio_from_apple(apple_episode_url):
    # Extract Episode ID
    episode_id_match = re.search(r'\?i=(\d+)', apple_episode_url)
    if not episode_id_match:
        print("Invalid Apple Podcast Episode URL format.")
        return

    # episode_id = episode_id_match.group(1)
    episode_name = apple_scraper.get_episode_title(apple_episode_url)
    print(f"Extracted Episode Name: {episode_name}")

    # Get RSS Feed URL
    rss_url = get_rss_from_apple_link(apple_episode_url)
    if not rss_url:
        print("Failed to retrieve RSS feed.")
        return
    
        # Check episode duration
    duration = get_duration_from_title(rss_url, episode_name)
    if duration and duration > 1800:
        return {
            "error": "Episode is longer than 30 minutes. Only shorter episodes are supported currently."
        }


    # Download Audio File
    data = download_audio_and_get_metadata(rss_url, episode_name)
    if data:
        print(f"Audio file saved at: {data['file_path']}")
        return data
    else:
        print("Failed to download audio.")

# Example usage:
# apple_url = "https://podcasts.apple.com/us/podcast/personalise-your-career-with-personal-guru/id1524691532?i=1000489323231"
# get_episode_audio_from_apple(apple_url)

# Example usage:
# episode_url = "https://open.spotify.com/episode/0tjyRC0PnkRiDW7SxvXadQ"
# show_url = "https://open.spotify.com/show/3QykqhdFj5Wu6UiH8kEXio"
# get_episode_audio_from_spotify(episode_url)
