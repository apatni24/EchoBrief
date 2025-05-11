from podcast_audio_resolver_service.apple_scraper import get_episode_title

def test_apple_episode_title_extraction():
    url = "https://podcasts.apple.com/us/podcast/juuust-asking/id1589145285?i=1000614437727"
    title = get_episode_title(url)
    assert isinstance(title, str)
    assert len(title) > 0
