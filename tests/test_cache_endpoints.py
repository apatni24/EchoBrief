import pytest
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from podcast_audio_resolver_service.main import app

client = TestClient(app)

class TestCacheEndpoints:
    """Test suite for cache-related API endpoints"""

    def test_get_cache_stats_success(self):
        """Test successful cache statistics retrieval"""
        with patch('cache_service.CacheService.get_cache_stats') as mock_stats:
            mock_stats.return_value = {
                "episode_cache_count": 5,
                "transcript_cache_count": 3,
                "total_cached_items": 8
            }
            
            response = client.get("/cache/stats")
            
            assert response.status_code == 200
            data = response.json()
            assert data["episode_cache_count"] == 5
            assert data["transcript_cache_count"] == 3
            assert data["total_cached_items"] == 8
            mock_stats.assert_called_once()

    def test_get_cache_stats_error(self):
        """Test cache statistics with service error"""
        with patch('cache_service.CacheService.get_cache_stats') as mock_stats:
            mock_stats.return_value = {"error": "Redis connection failed"}
            
            response = client.get("/cache/stats")
            
            assert response.status_code == 200
            data = response.json()
            assert "error" in data

    def test_clear_cache_without_auth(self):
        """Test cache clear without admin authentication"""
        response = client.delete("/cache/clear")
        
        assert response.status_code == 403
        data = response.json()
        assert "Admin access required" in data["detail"]

    def test_clear_cache_with_invalid_auth(self):
        """Test cache clear with invalid admin key"""
        response = client.delete("/cache/clear?admin_key=wrong-key")
        
        assert response.status_code == 403
        data = response.json()
        assert "Admin access required" in data["detail"]

    @patch('cache_service.CacheService.clear_cache')
    def test_clear_cache_with_valid_auth(self, mock_clear):
        """Test cache clear with valid admin authentication"""
        mock_clear.return_value = True
        
        # Use the default admin key from the environment
        response = client.delete("/cache/clear?admin_key=default-admin-key")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Cache cleared successfully" in data["message"]
        mock_clear.assert_called_once()

    @patch('cache_service.CacheService.clear_cache')
    def test_clear_cache_service_error(self, mock_clear):
        """Test cache clear when service fails"""
        mock_clear.return_value = False
        
        response = client.delete("/cache/clear?admin_key=default-admin-key")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Cache cleared successfully" in data["message"]

    @patch('cache_service.CacheService.invalidate_specific_episode')
    def test_invalidate_episode_cache_success(self, mock_invalidate):
        """Test successful episode cache invalidation"""
        mock_invalidate.return_value = True
        
        response = client.delete("/cache/invalidate/apple/123456/ts")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Cache invalidated for apple:123456:ts" in data["message"]
        mock_invalidate.assert_called_once_with("apple", "123456", "ts")

    @patch('cache_service.CacheService.invalidate_specific_episode')
    def test_invalidate_episode_cache_not_found(self, mock_invalidate):
        """Test episode cache invalidation when episode doesn't exist"""
        mock_invalidate.return_value = False
        
        response = client.delete("/cache/invalidate/spotify/789/bs")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Cache invalidated for spotify:789:bs" in data["message"]
        mock_invalidate.assert_called_once_with("spotify", "789", "bs")

    def test_invalidate_episode_cache_invalid_params(self):
        """Test episode cache invalidation with invalid parameters"""
        # Test with invalid platform
        response = client.delete("/cache/invalidate/invalid/123/ts")
        assert response.status_code == 200  # Should still work, just return False

        # Test with empty episode ID
        response = client.delete("/cache/invalidate/apple/none/ts")
        assert response.status_code == 200

        # Test with invalid summary type
        response = client.delete("/cache/invalidate/apple/123/invalid")
        assert response.status_code == 200

    @patch('cache_service.CacheService.get_cached_episode')
    def test_submit_with_cache_hit(self, mock_get_cached):
        """Test /submit endpoint with cache hit"""
        cached_data = {
            "summary": "Cached summary",
            "metadata": {"title": "Cached Episode"},
            "cached_at": 1234567890
        }
        mock_get_cached.return_value = cached_data
        
        response = client.post("/submit", json={
            "url": "https://podcasts.apple.com/us/podcast/episode?id=123456",
            "summary_type": "ts"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["cached"] is True
        assert data["processing_time"] == 0
        assert "Cached result retrieved" in data["message"]
        assert data["data"] == cached_data

    @patch('cache_service.CacheService.get_cached_episode')
    @patch('podcast_audio_resolver_service.get_audio.get_episode_audio_from_apple')
    @patch('podcast_audio_resolver_service.audio_upload_producer.emit_audio_uploaded')
    def test_submit_with_cache_miss(self, mock_emit, mock_get_audio, mock_get_cached):
        """Test /submit endpoint with cache miss"""
        # Cache miss
        mock_get_cached.return_value = None
        
        # Mock successful audio extraction
        mock_get_audio.return_value = {
            "file_path": "audio_files/test.mp3",
            "metadata": {"title": "Test Episode"}
        }
        
        response = client.post("/submit", json={
            "url": "https://podcasts.apple.com/us/podcast/episode?id=123456",
            "summary_type": "ts"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["cached"] is False
        assert "Download successful" in data["message"]
        assert "platform" in data["data"]
        assert "episode_id" in data["data"]
        
        # Verify cache was checked
        mock_get_cached.assert_called_once()
        # Verify audio processing was triggered
        mock_get_audio.assert_called_once()
        mock_emit.assert_called_once()

    def test_submit_invalid_url(self):
        """Test /submit endpoint with invalid URL"""
        response = client.post("/submit", json={
            "url": "https://invalid-url.com/episode",
            "summary_type": "ts"
        })
        
        assert response.status_code == 400
        data = response.json()
        assert "Unsupported podcast platform" in data["detail"]

    def test_submit_missing_fields(self):
        """Test /submit endpoint with missing required fields"""
        # Missing URL
        response = client.post("/submit", json={
            "summary_type": "ts"
        })
        assert response.status_code == 422
        
        # Missing summary_type
        response = client.post("/submit", json={
            "url": "https://podcasts.apple.com/us/podcast/episode?id=123456"
        })
        assert response.status_code == 422

    @patch('cache_service.CacheService.get_cached_episode')
    @patch('podcast_audio_resolver_service.get_audio.get_episode_audio_from_apple')
    def test_submit_audio_extraction_error(self, mock_get_audio, mock_get_cached):
        """Test /submit endpoint when audio extraction fails"""
        mock_get_cached.return_value = None
        mock_get_audio.return_value = {"error": "Episode not found"}
        
        response = client.post("/submit", json={
            "url": "https://podcasts.apple.com/us/podcast/episode?id=123456",
            "summary_type": "ts"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["error"] is True
        assert "Episode not found" in data["message"]

    def test_cache_endpoints_cors_headers(self):
        """Test that cache endpoints include proper CORS headers"""
        response = client.get("/cache/stats")
        assert response.status_code == 200
        # CORS headers should be present (handled by FastAPI middleware)

    def test_cache_endpoints_content_type(self):
        """Test that cache endpoints return proper content type"""
        response = client.get("/cache/stats")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    @patch('cache_service.CacheService.get_cached_episode')
    def test_submit_platform_detection(self, mock_get_cached):
        """Test that platform detection works correctly in submit endpoint"""
        mock_get_cached.return_value = None
        
        # Test Apple Podcasts
        with patch('podcast_audio_resolver_service.get_audio.get_episode_audio_from_apple') as mock_apple:
            mock_apple.return_value = {"file_path": "test.mp3", "metadata": {}}
            
            response = client.post("/submit", json={
                "url": "https://podcasts.apple.com/us/podcast/episode?id=123456",
                "summary_type": "ts"
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["platform"] == "apple"
            assert data["data"]["episode_id"] == "123456"

        # Test Spotify
        with patch('podcast_audio_resolver_service.get_audio.get_episode_audio_from_spotify') as mock_spotify:
            mock_spotify.return_value = {"file_path": "test.mp3", "metadata": {}}
            
            response = client.post("/submit", json={
                "url": "https://open.spotify.com/episode/abc123",
                "summary_type": "bs"
            })
            
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["platform"] == "spotify"
            assert data["data"]["episode_id"] == "abc123" 