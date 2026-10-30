"""POST /submit keeps the human JSON shape on cache hit and cache miss."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from podcast_audio_resolver_service.main import app

client = TestClient(app)

APPLE = "https://podcasts.apple.com/us/podcast/episode?i=123456"


@patch("cache_service.CacheService.get_cached_episode")
def test_submit_cache_hit_shape(mock_get_cached):
    cached_data = {
        "summary": "Cached summary",
        "metadata": {"title": "Cached Episode"},
        "cached_at": 1234567890,
    }
    mock_get_cached.return_value = cached_data

    response = client.post("/submit", json={"url": APPLE, "summary_type": "ts"})

    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {"message", "data", "error", "cached", "processing_time"}
    assert data["message"] == "Cached result retrieved"
    assert data["error"] is False
    assert data["cached"] is True
    assert data["processing_time"] == 0
    assert data["data"] == cached_data
    assert "job_id" not in data["data"]


@patch("cache_service.CacheService.get_cached_episode")
@patch("podcast_audio_resolver_service.get_audio.get_episode_audio_from_apple")
@patch("podcast_audio_resolver_service.audio_upload_producer.emit_audio_uploaded")
def test_submit_cache_miss_shape(mock_emit, mock_get_audio, mock_get_cached):
    mock_get_cached.return_value = None
    mock_get_audio.return_value = {
        "file_path": "audio_files/test.mp3",
        "metadata": {"title": "Test Episode", "duration": 600},
    }

    response = client.post("/submit", json={"url": APPLE, "summary_type": "ts"})

    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {"message", "data", "error", "cached"}
    assert data["message"] == "Download successful"
    assert data["error"] is False
    assert data["cached"] is False
    assert data["data"]["job_id"]
    assert data["data"]["platform"] == "apple"
    assert data["data"]["episode_id"] == "123456"
    assert "processing_time" not in data
    mock_get_audio.assert_called_once()
    mock_emit.assert_called_once()


def test_submit_validation_details_unchanged():
    missing = client.post("/submit", json={"summary_type": "ts"})
    assert missing.status_code == 422

    empty = client.post("/submit", json={"url": "   ", "summary_type": "ts"})
    assert empty.status_code == 400
    assert empty.json()["detail"] == "URL is required"

    bad_type = client.post("/submit", json={"url": APPLE, "summary_type": "nope"})
    assert bad_type.status_code == 400
    assert bad_type.json()["detail"] == "Invalid summary type. Must be 'ts', 'ns', or 'bs'"

    bad_platform = client.post("/submit", json={"url": "https://example.com/show", "summary_type": "ts"})
    assert bad_platform.status_code == 400
    assert "Unsupported podcast platform" in bad_platform.json()["detail"]
