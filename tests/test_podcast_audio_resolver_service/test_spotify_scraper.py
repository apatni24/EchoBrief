from podcast_audio_resolver_service.spotify_scraper import get_show_and_episode_title

def test_spotify_episode_url_parsing():
    url = "https://open.spotify.com/episode/6yBqTVa5h5ZrvcgdOTH0Kc"
    titles = get_show_and_episode_title(url)
    assert isinstance(titles, list)
    assert len(titles) == 2
    assert all(isinstance(t, str) for t in titles)
