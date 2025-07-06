from podcast_audio_resolver_service.spotify_scraper import get_show_and_episode_title
from podcast_audio_resolver_service import apple_scraper
from podcast_audio_resolver_service.rss_fetcher import get_rss_feed_url, get_rss_from_apple_link
from podcast_audio_resolver_service.audio_extractor import download_audio_and_get_metadata
from podcast_audio_resolver_service.duration_checker import get_duration_from_episode
from podcast_audio_resolver_service.podcast_index_episode_byfeedurl import get_episode_from_title
from podcast_audio_resolver_service.get_image import get_image_url_from_episode

import re

def get_episode_audio_from_spotify(episode_url):
    try:
        print("Fetching episode and show titles...")
        titles = get_show_and_episode_title(episode_url)
        
        if not titles or len(titles) < 2:
            return {
                "error": "Could not extract episode and show titles from Spotify URL."
            }

        titles = [title.rstrip() for title in titles]
        print(f"Podcast: \"{titles[1]}\", Episode: \"{titles[0]}\"")

        print("Fetching RSS feed...")
        rss_url = get_rss_feed_url(titles[1])

        if not rss_url:
            return {
                "error": f"RSS feed not found for podcast: {titles[1]}"
            }

        print("Extracting audio URL...")
        data = download_audio_and_get_metadata(rss_url, titles[0])

        if data and "error" not in data:
            return data
        elif data and "error" in data:
            return data
        else:
            return {
                "error": "Failed to retrieve audio URL or metadata."
            }
            
    except Exception as e:
        print(f"Error in get_episode_audio_from_spotify: {e}")
        return {
            "error": f"Failed to process Spotify episode: {str(e)}"
        }

def get_episode_audio_from_apple(apple_episode_url):
    try:
        # Extract Episode ID
        episode_id_match = re.search(r'[?&]i=(\d+)', apple_episode_url)
        if not episode_id_match:
            episode_id_match = re.search(r'[?&]id=(\d+)', apple_episode_url)
        if not episode_id_match:
            return {
                "error": "Invalid Apple Podcast Episode URL format."
            }

        episode_name = apple_scraper.get_episode_title(apple_episode_url)
        if not episode_name:
            return {
                "error": "Could not extract episode title from Apple Podcast URL."
            }
            
        print(f"Extracted Episode Name: {episode_name}")

        # Get RSS Feed URL
        rss_url = get_rss_from_apple_link(apple_episode_url)
        if not rss_url:
            return {
                "error": "Failed to retrieve RSS feed from Apple Podcast link."
            }

        # Download Audio File
        data = download_audio_and_get_metadata(rss_url, episode_name)
        
        if data and "error" not in data:
            return data
        elif data and "error" in data:
            return data
        else:
            return {
                "error": "Failed to download audio or extract metadata."
            }
            
    except Exception as e:
        print(f"Error in get_episode_audio_from_apple: {e}")
        return {
            "error": f"Failed to process Apple Podcast episode: {str(e)}"
        }

# Example usage:
# apple_url = "https://podcasts.apple.com/us/podcast/personalise-your-career-with-personal-guru/id1524691532?i=1000489323231"
# get_episode_audio_from_apple(apple_url)

# Example usage:
# episode_url = "https://open.spotify.com/episode/0tjyRC0PnkRiDW7SxvXadQ"
# show_url = "https://open.spotify.com/show/3QykqhdFj5Wu6UiH8kEXio"
# get_episode_audio_from_spotify(episode_url)
