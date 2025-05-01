import requests
from bs4 import BeautifulSoup

def get_podcast_title(show_url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(show_url, headers=headers)

    if response.status_code != 200:
        print(f"Failed to fetch page. Status code: {response.status_code}")
        return None
    
    response.encoding = 'utf-8'
    
    soup = BeautifulSoup(response.text, 'html.parser')
    raw_title = soup.title.string
    return raw_title.replace(" | Podcast on Spotify", "").strip()

def get_show_and_episode_title(episode_url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(episode_url, headers=headers)

    if response.status_code != 200:
        print(f"Failed to fetch page. Status code: {response.status_code}")
        return None
    
    response.encoding = 'utf-8'

    soup = BeautifulSoup(response.text, 'html.parser')

    # print(soup)

    episode_title_span = soup.find('h1', {'data-testid': 'episodeTitle'})
    episode_title = episode_title_span.text if episode_title_span else None

    show_title_span = soup.find('p', {'data-testid': 'entity-header-entity-subtitle'})
    show_title = show_title_span.text if show_title_span else None

    return [episode_title, show_title]

# Example:
# print(get_podcast_title("https://open.spotify.com/show/xyz"))
# print(get_episode_title("https://open.spotify.com/episode/abc"))

# print(get_show_and_episode_title("https://open.spotify.com/episode/6FkkcQIo0bvqOCJ4KG5t2e"))