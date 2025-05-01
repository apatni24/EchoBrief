import requests
from bs4 import BeautifulSoup

def get_episode_title(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"Failed to fetch page. Status code: {response.status_code}")
        return None
    
    response.encoding = 'utf-8'

    soup = BeautifulSoup(response.text, 'html.parser')

    # Find the <h1> tag with class 'headings__title'
    h1_tag = soup.find('h1', class_='headings__title')

    if not h1_tag:
        print("Could not find the h1 with class 'headings__title'")
        return None

    # Find the <span> inside the <h1>
    span_tag = h1_tag.find('span')

    if not span_tag:
        print("No <span> found inside the <h1> tag.")
        return None

    title = span_tag.text.strip()
    print(f"Extracted Title: {title}")
    return title

# Example usage:
# url = "https://podcasts.apple.com/us/podcast/episode-3-the-chief/id1789644662?i=1000699606683"
# scrape_episode_title(url)

# get_episode_title("https://podcasts.apple.com/us/podcast/the-climate-movement-needs-new-stories-heres-mine/id160904630?i=1000705000078")