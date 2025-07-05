import pytest
import json
import time
from unittest.mock import patch, MagicMock
from cache_service import CacheService

class TestCacheService:
    """Test suite for CacheService"""

    def test_extract_episode_id_apple(self):
        """Test Apple Podcasts episode ID extraction"""
        url = "https://podcasts.apple.com/us/podcast/how-to-stay-calm-in-emergency-situations/id1461493560?i=1000708510035"
        episode_id = CacheService.extract_episode_id(url)
        assert episode_id == "1000708510035"

    def test_extract_episode_id_spotify(self):
        """Test Spotify episode ID extraction"""
        url = "https://open.spotify.com/episode/0tjyRC0PnkRiDW7SxvXadQ"
        episode_id = CacheService.extract_episode_id(url)
        assert episode_id == "0tjyRC0PnkRiDW7SxvXadQ"

    def test_extract_episode_id_invalid(self):
        """Test episode ID extraction for invalid URLs"""
        url = "https://invalid-url.com/episode/123"
        episode_id = CacheService.extract_episode_id(url)
        # Should return MD5 hash of URL
        assert len(episode_id) == 32
        assert episode_id.isalnum()

    def test_get_platform_apple(self):
        """Test platform detection for Apple Podcasts"""
        url = "https://podcasts.apple.com/us/podcast/episode"
        platform = CacheService.get_platform(url)
        assert platform == "apple"

    def test_get_platform_spotify(self):
        """Test platform detection for Spotify"""
        url = "https://open.spotify.com/episode/123"
        platform = CacheService.get_platform(url)
        assert platform == "spotify"

    def test_get_platform_unknown(self):
        """Test platform detection for unknown URLs"""
        url = "https://unknown-platform.com/episode/123"
        platform = CacheService.get_platform(url)
        assert platform == "unknown"

    def test_generate_episode_key(self):
        """Test cache key generation"""
        key = CacheService._generate_episode_key("apple", "123456", "ts")
        expected = "episode:apple:123456:ts"
        assert key == expected

    @patch('cache_service.redis_client')
    def test_get_cached_episode_hit(self, mock_redis):
        """Test successful cache retrieval"""
        # Mock cached data
        cached_data = {
            "summary": "Test summary",
            "metadata": {"title": "Test Episode"},
            "cached_at": time.time()
        }
        mock_redis.get.return_value = json.dumps(cached_data)
        
        result = CacheService.get_cached_episode("apple", "123456", "ts")
        
        assert result == cached_data
        mock_redis.get.assert_called_once_with("episode:apple:123456:ts")

    @patch('cache_service.redis_client')
    def test_get_cached_episode_miss(self, mock_redis):
        """Test cache miss scenario"""
        mock_redis.get.return_value = None
        
        result = CacheService.get_cached_episode("apple", "123456", "ts")
        
        assert result is None
        mock_redis.get.assert_called_once_with("episode:apple:123456:ts")

    @patch('cache_service.redis_client')
    def test_get_cached_episode_error(self, mock_redis):
        """Test cache retrieval with Redis error"""
        mock_redis.get.side_effect = Exception("Redis connection error")
        
        result = CacheService.get_cached_episode("apple", "123456", "ts")
        
        assert result is None

    @patch('cache_service.redis_client')
    def test_set_cached_episode_success(self, mock_redis):
        """Test successful cache storage"""
        episode_data = {
            "summary": "Test summary",
            "metadata": {"title": "Test Episode"}
        }
        
        result = CacheService.set_cached_episode("apple", "123456", "ts", episode_data)
        
        assert result is True
        mock_redis.setex.assert_called_once()
        
        # Verify the call arguments
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "episode:apple:123456:ts"  # key
        assert call_args[0][1] == CacheService.EPISODE_CACHE_TTL  # ttl
        
        # Verify the cached data includes additional fields
        cached_data = json.loads(call_args[0][2])
        assert "summary" in cached_data
        assert "metadata" in cached_data
        assert "cached_at" in cached_data
        assert "cache_ttl" in cached_data

    @patch('cache_service.redis_client')
    def test_set_cached_episode_error(self, mock_redis):
        """Test cache storage with Redis error"""
        mock_redis.setex.side_effect = Exception("Redis connection error")
        
        episode_data = {"summary": "Test summary"}
        result = CacheService.set_cached_episode("apple", "123456", "ts", episode_data)
        
        assert result is False

    @patch('cache_service.redis_client')
    def test_invalidate_specific_episode_success(self, mock_redis):
        """Test successful episode cache invalidation"""
        mock_redis.delete.return_value = 1
        
        result = CacheService.invalidate_specific_episode("apple", "123456", "ts")
        
        assert result is True
        mock_redis.delete.assert_called_once_with("episode:apple:123456:ts")

    @patch('cache_service.redis_client')
    def test_invalidate_specific_episode_not_found(self, mock_redis):
        """Test episode cache invalidation when key doesn't exist"""
        mock_redis.delete.return_value = 0
        
        result = CacheService.invalidate_specific_episode("apple", "123456", "ts")
        
        assert result is False
        mock_redis.delete.assert_called_once_with("episode:apple:123456:ts")

    @patch('cache_service.redis_client')
    def test_invalidate_specific_episode_error(self, mock_redis):
        """Test episode cache invalidation with Redis error"""
        mock_redis.delete.side_effect = Exception("Redis connection error")
        
        result = CacheService.invalidate_specific_episode("apple", "123456", "ts")
        
        assert result is False

    @patch('cache_service.redis_client')
    def test_get_cache_stats_success(self, mock_redis):
        """Test successful cache statistics retrieval"""
        # Mock keys for different cache entries
        mock_keys = [
            "episode:apple:123:ts",
            "episode:spotify:456:bs",
            "episode:apple:789:ns"
        ]
        mock_redis.keys.return_value = mock_keys
        
        stats = CacheService.get_cache_stats()
        
        expected_stats = {
            "episode_cache_count": 3,
            "total_cached_items": 3
        }
        assert stats == expected_stats
        mock_redis.keys.assert_called_once_with("episode:*")

    @patch('cache_service.redis_client')
    def test_get_cache_stats_error(self, mock_redis):
        """Test cache statistics retrieval with Redis error"""
        mock_redis.keys.side_effect = Exception("Redis connection error")
        
        stats = CacheService.get_cache_stats()
        
        assert "error" in stats

    @patch('cache_service.redis_client')
    def test_clear_cache_success(self, mock_redis):
        """Test successful cache clearing"""
        mock_keys = ["episode:apple:123:ts", "episode:spotify:456:bs"]
        mock_redis.keys.return_value = mock_keys
        mock_redis.delete.return_value = 2
        
        result = CacheService.clear_cache()
        
        assert result is True
        mock_redis.keys.assert_called_once_with("episode:*")
        mock_redis.delete.assert_called_once_with(*mock_keys)

    @patch('cache_service.redis_client')
    def test_clear_cache_empty(self, mock_redis):
        """Test cache clearing when cache is empty"""
        mock_redis.keys.return_value = []
        
        result = CacheService.clear_cache()
        
        assert result is True
        mock_redis.keys.assert_called_once_with("episode:*")
        mock_redis.delete.assert_not_called()

    @patch('cache_service.redis_client')
    def test_clear_cache_error(self, mock_redis):
        """Test cache clearing with Redis error"""
        mock_redis.keys.side_effect = Exception("Redis connection error")
        
        result = CacheService.clear_cache()
        
        assert result is False

    def test_cache_ttl_value(self):
        """Test that cache TTL is set correctly"""
        # 7 days in seconds
        expected_ttl = 7 * 24 * 60 * 60
        assert CacheService.EPISODE_CACHE_TTL == expected_ttl

    def test_cache_prefix_consistency(self):
        """Test cache prefix consistency"""
        assert CacheService.EPISODE_CACHE_PREFIX == "episode"

    @patch('cache_service.redis_client')
    def test_cache_data_structure(self, mock_redis):
        """Test that cached data has the correct structure"""
        episode_data = {
            "summary": "Test summary",
            "metadata": {"title": "Test Episode"},
            "summary_type": "ts",
            "transcript_length": 1000
        }
        
        CacheService.set_cached_episode("apple", "123456", "ts", episode_data)
        
        # Get the cached data that was stored
        call_args = mock_redis.setex.call_args
        cached_data = json.loads(call_args[0][2])
        
        # Verify all required fields are present
        assert "summary" in cached_data
        assert "metadata" in cached_data
        assert "summary_type" in cached_data
        assert "transcript_length" in cached_data
        assert "cached_at" in cached_data
        assert "cache_ttl" in cached_data
        
        # Verify data types
        assert isinstance(cached_data["cached_at"], (int, float))
        assert isinstance(cached_data["cache_ttl"], int)
        assert cached_data["cache_ttl"] == CacheService.EPISODE_CACHE_TTL 