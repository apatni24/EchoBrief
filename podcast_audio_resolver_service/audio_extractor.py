import os
import requests
import feedparser
import hashlib
import json
from pathlib import Path

# Cache file to store audio URL to local file mappings
CACHE_FILE = "audio_files/download_cache.json"

def load_download_cache():
    """Load the download cache from file"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️ Error loading download cache: {e}")
    return {}

def save_download_cache(cache):
    """Save the download cache to file"""
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"⚠️ Error saving download cache: {e}")

def find_existing_audio_file(audio_url, episode_title):
    """
    Check if audio file already exists locally.
    Returns (file_path, file_hash) if found, (None, None) if not found.
    """
    # Clean the audio URL for comparison
    clean_url = audio_url.split('?')[0]
    
    # Load existing cache
    cache = load_download_cache()
    
    # Check if URL exists in cache
    if clean_url in cache:
        cached_file_path = cache[clean_url]["file_path"]
        cached_file_hash = cache[clean_url]["file_hash"]
        
        # Verify file still exists
        if os.path.exists(cached_file_path):
            print(f"🎯 Found existing audio file: {cached_file_path}")
            print(f"🎯 Using cached file hash: {cached_file_hash[:8]}...")
            return cached_file_path, cached_file_hash
        else:
            print(f"⚠️ Cached file not found, removing from cache: {cached_file_path}")
            del cache[clean_url]
            save_download_cache(cache)
    
    # Fallback: Check by episode title (for files downloaded before cache was implemented)
    folder = 'audio_files'
    if os.path.exists(folder):
        for filename in os.listdir(folder):
            if filename.endswith(('.mp3', '.m4a', '.wav')):
                # Check if episode title is in filename
                if episode_title.lower().replace(' ', '_').replace('/', '-') in filename.lower():
                    file_path = os.path.join(folder, filename)
                    print(f"🎯 Found existing audio file by title: {file_path}")
                    
                    # Compute hash for the existing file
                    print(f"🔄 Computing hash for existing file...")
                    hash_md5 = hashlib.md5()
                    with open(file_path, 'rb') as f:
                        for chunk in iter(lambda: f.read(8192), b""):
                            hash_md5.update(chunk)
                    file_hash = hash_md5.hexdigest()
                    
                    # Add to cache for future use
                    cache[clean_url] = {
                        "file_path": file_path,
                        "file_hash": file_hash,
                        "episode_title": episode_title
                    }
                    save_download_cache(cache)
                    
                    print(f"💾 Added existing file to cache")
                    return file_path, file_hash
    
    print(f"❌ No existing audio file found for: {episode_title}")
    return None, None

def get_episode_audio_file_with_episode_title(episode_entry, episode_title):
    audio_url = episode_entry.enclosures[0]['href']
    audio_url = audio_url.split('?')[0]
    print(f"Found Audio URL: {audio_url}")
    
    # Check if file already exists locally
    existing_file_path, existing_file_hash = find_existing_audio_file(audio_url, episode_title)
    if existing_file_path and existing_file_hash:
        return existing_file_path, existing_file_hash
    
    # File doesn't exist, proceed with download
    # Detect file extension from URL
    ext = os.path.splitext(audio_url)[1]  # Gets '.m4a' or '.mp3'
    if not ext:
        ext = '.mp3'  # Default fallback
    
    # Generate safe filename
    filename = episode_title.strip().replace(' ', '_').replace('/', '-') + ext
    folder = 'audio_files'
    os.makedirs(folder, exist_ok=True)
    file_path = os.path.join(folder, filename)
    
    # Download the audio file and compute hash simultaneously
    print(f"Downloading to {file_path} ...")
    hash_md5 = hashlib.md5()
    
    with requests.get(audio_url, stream=True) as r:
        r.raise_for_status()
        with open(file_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                hash_md5.update(chunk)  # Compute hash during download
    
    file_hash = hash_md5.hexdigest()
    print(f"Download complete: {file_path}")
    print(f"File hash: {file_hash}")
    
    # Add to download cache
    cache = load_download_cache()
    cache[audio_url] = {
        "file_path": file_path,
        "file_hash": file_hash,
        "episode_title": episode_title
    }
    save_download_cache(cache)
    print(f"💾 Added to download cache")
    
    return file_path, file_hash

def download_episode_audio_with_episode_id(rss_url, apple_episode_id):
    """
    Parse RSS feed, find the episode by Episode ID, and download the audio file.
    """
    feed = feedparser.parse(rss_url)

    for entry in feed.entries:
        guid = entry.get('guid', '')
        link = entry.get('link', '')

        if apple_episode_id in guid or apple_episode_id in link:
            audio_url = entry.enclosures[0]['href']
            episode_title = entry.title

            # Check if file already exists locally
            existing_file_path, existing_file_hash = find_existing_audio_file(audio_url, episode_title)
            if existing_file_path and existing_file_hash:
                return existing_file_path, existing_file_hash

            # File doesn't exist, proceed with download
            # Get file extension from URL
            ext = os.path.splitext(audio_url)[1]
            if not ext:
                ext = '.mp3'

            # Prepare filename and folder
            safe_title = entry.title.strip().replace(' ', '_').replace('/', '-')
            filename = f"{safe_title}{ext}"
            folder = 'audio_files'
            os.makedirs(folder, exist_ok=True)
            file_path = os.path.join(folder, filename)

            # Download audio file and compute hash simultaneously
            print(f"Downloading audio to {file_path} ...")
            hash_md5 = hashlib.md5()
            
            with requests.get(audio_url, stream=True) as r:
                r.raise_for_status()
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        hash_md5.update(chunk)  # Compute hash during download

            file_hash = hash_md5.hexdigest()
            print(f"Download complete: {file_path}")
            print(f"File hash: {file_hash}")
            
            # Add to download cache
            cache = load_download_cache()
            cache[audio_url] = {
                "file_path": file_path,
                "file_hash": file_hash,
                "episode_title": episode_title
            }
            save_download_cache(cache)
            print(f"💾 Added to download cache")
            
            return file_path, file_hash

    print("Episode ID not found in RSS feed.")
    return None, None

def get_show_title(feed):
    return feed.feed.title

def get_show_summary(feed):
    try:
        return feed.feed.summary
    except :
        return ""


def duration_to_seconds(duration_str: str) -> int:
    """
    Convert a duration string 'HH:MM:SS' into total seconds.
    """
    hours, minutes, seconds = map(int, duration_str.split(':'))
    return hours * 3600 + minutes * 60 + seconds



def download_audio_and_get_metadata(rss_url, episode_title):
    try:
        print("processing rss url")
        feed = feedparser.parse(rss_url)
        episode_entry = None
        for entry in feed.entries:
            if(episode_title.lower() in entry.title.lower()):
                episode_entry = entry
                break
        if not episode_entry:
            return {
                "file_path": None
            }
        print(episode_entry)
        duration = episode_entry.itunes_duration
        if(duration):
            try:
                duration = duration_to_seconds(duration)
            except:
                duration = int(duration)
        print(duration)
        if duration and duration > 1800:
            return {
                "error": "Episode is longer than 30 minutes. Only shorter episodes are supported currently."
            }
        summary = episode_entry.summary
        show_title = get_show_title(feed)
        show_summary = get_show_summary(feed)
        file_path, file_hash = get_episode_audio_file_with_episode_title(episode_entry, episode_title)
        image_url = episode_entry.image.href
        
        return {
            "file_path": file_path,
            "file_hash": file_hash,
            "metadata": {
                "summary": summary,
                "show_title": show_title,
                "show_summary": show_summary,
                "episode_title": episode_title,
                "image_url": image_url,
                "duration": duration
            }
        }
    except Exception as err:
        print(err)
        return {
            "error": err
        }
