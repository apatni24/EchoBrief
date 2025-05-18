import os
import requests
import feedparser

def get_episode_audio_file_with_episode_title(episode_entry, episode_title):
    audio_url = episode_entry.enclosures[0]['href']
    audio_url = audio_url.split('?')[0]
    print(f"Found Audio URL: {audio_url}")
    
    # Detect file extension from URL
    ext = os.path.splitext(audio_url)[1]  # Gets '.m4a' or '.mp3'
    if not ext:
        ext = '.mp3'  # Default fallback
    
    # Generate safe filename
    filename = episode_title.strip().replace(' ', '_').replace('/', '-') + ext
    folder = 'audio_files'
    os.makedirs(folder, exist_ok=True)
    file_path = os.path.join(folder, filename)
    
    # Download the audio file
    print(f"Downloading to {file_path} ...")
    with requests.get(audio_url, stream=True) as r:
        r.raise_for_status()
        with open(file_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    
    print(f"Download complete: {file_path}")
    return file_path

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

            # Download audio file
            print(f"Downloading audio to {file_path} ...")
            with requests.get(audio_url, stream=True) as r:
                r.raise_for_status()
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

            print(f"Download complete: {file_path}")
            return file_path

    print("Episode ID not found in RSS feed.")
    return None

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
        file_path = get_episode_audio_file_with_episode_title(episode_entry, episode_title)
        image_url = episode_entry.image.href
        
        return {
            "file_path": file_path,
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
