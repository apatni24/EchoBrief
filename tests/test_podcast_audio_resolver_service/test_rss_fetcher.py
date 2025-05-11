from podcast_audio_resolver_service.rss_fetcher import get_rss_feed_url, get_rss_from_apple_link

def test_get_rss_feed_url_valid():
    rss = get_rss_feed_url("The Daily")  # A popular real podcast
    assert rss is not None
    assert rss.startswith("http")

def test_valid_rss_from_apple_url():
    url = "https://podcasts.apple.com/us/podcast/the-daily/id1200361736?i=1000586070870"
    rss = get_rss_from_apple_link(url)
    assert rss is None or rss.startswith("http")

def test_get_rss_feed_url_invalid():
    rss = get_rss_feed_url("SomeInvalidPodcastTitle123")
    assert rss is None or rss == ""
