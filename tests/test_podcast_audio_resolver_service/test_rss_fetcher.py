import pytest
from unittest.mock import patch
from podcast_audio_resolver_service import rss_fetcher


@patch("podcast_audio_resolver_service.rss_fetcher.requests.post")
def test_get_rss_feed_url_valid(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "feeds": [{"url": "http://example.com/feed.xml"}]
    }

    rss = rss_fetcher.get_rss_feed_url("The Daily")
    assert rss == "http://example.com/feed.xml"


@patch("podcast_audio_resolver_service.rss_fetcher.requests.get")
def test_valid_rss_from_apple_url(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "feed": {"url": "http://example.com/rss.xml"}
    }

    url = "https://podcasts.apple.com/us/podcast/the-daily/id1200361736?i=1000586070870"
    rss = rss_fetcher.get_rss_from_apple_link(url)
    assert rss == "http://example.com/rss.xml"


@patch("podcast_audio_resolver_service.rss_fetcher.requests.post")
def test_get_rss_feed_url_invalid(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"feeds": []}

    rss = rss_fetcher.get_rss_feed_url("SomeInvalidPodcastTitle123")
    assert rss is None
