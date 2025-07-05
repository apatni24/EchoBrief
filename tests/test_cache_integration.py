import pytest
import json
import time
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from podcast_audio_resolver_service.main import app
from summarization_service.transcription_complete_consumer import consume_transcription_completed
from cache_service import CacheService

client = TestClient(app)

class TestCacheIntegration:
    """Integration tests for complete cache flow"""

    @patch('redis_stream_client.redis_client')
    @patch('podcast_audio_resolver_service.get_audio.get_episode_audio_from_apple')
    @patch('podcast_audio_resolver_service.audio_upload_producer.emit_audio_uploaded')
    def test_complete_cache_flow(self, mock_emit, mock_get_audio, mock_redis):
        """Test complete flow: cache miss -> processing -> cache storage -> cache hit"""
        
        # Step 1: Initial cache miss
        mock_redis.get.return_value = None  # Cache miss
        
        # Mock successful audio extraction
        mock_get_audio.return_value = {
            "file_path": "audio_files/test.mp3",
            "metadata": {
                "summary": "Test episode summary",
                "show_title": "Test Show",
                "show_summary": "Test show description"
            }
        }
        
        # Step 2: Submit request (should trigger processing)
        response = client.post("/submit", json={
            "url": "https://podcasts.apple.com/us/podcast/episode?id=123456",
            "summary_type": "ts"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["cached"] is False
        assert "Download successful" in data["message"]
        
        # Verify cache was checked
        mock_redis.get.assert_called_once_with("episode:apple:123456:ts")
        
        # Step 3: Simulate transcription completion and cache storage
        transcription_data = {
            "job_id": "test-job-123",
            "platform": "apple",
            "episode_id": "123456",
            "summary_type": "ts",
            "transcript": "This is a test transcript of the podcast episode.",
            "metadata": {
                "summary": "Test episode summary",
                "show_title": "Test Show",
                "show_summary": "Test show description"
            },
            "file_path": "audio_files/test.mp3"
        }
        
        # Mock cache storage
        mock_redis.setex.return_value = True
        
        # Simulate cache storage
        CacheService.set_cached_episode(
            transcription_data["platform"],
            transcription_data["episode_id"],
            transcription_data["summary_type"],
            {
                "summary": "Generated summary from AI",
                "metadata": transcription_data["metadata"],
                "summary_type": transcription_data["summary_type"],
                "transcript_length": len(transcription_data["transcript"]),
                "processing_time": 45,
                "file_path": transcription_data["file_path"]
            }
        )
        
        # Step 4: Submit same request again (should be cache hit)
        mock_redis.get.return_value = json.dumps({
            "summary": "Generated summary from AI",
            "metadata": transcription_data["metadata"],
            "summary_type": "ts",
            "transcript_length": len(transcription_data["transcript"]),
            "processing_time": 45,
            "file_path": "audio_files/test.mp3",
            "cached_at": time.time(),
            "cache_ttl": CacheService.EPISODE_CACHE_TTL
        })
        
        response2 = client.post("/submit", json={
            "url": "https://podcasts.apple.com/us/podcast/episode?id=123456",
            "summary_type": "ts"
        })
        
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["cached"] is True
        assert data2["processing_time"] == 0
        assert "Cached result retrieved" in data2["message"]
        
        # Verify cache was checked again
        assert mock_redis.get.call_count == 2

    @patch('redis_stream_client.redis_client')
    def test_cache_different_summary_types(self, mock_redis):
        """Test that different summary types are cached separately"""
        
        # Mock cache miss for both types
        mock_redis.get.return_value = None
        
        # Submit request for bullet points
        response1 = client.post("/submit", json={
            "url": "https://podcasts.apple.com/us/podcast/episode?id=123456",
            "summary_type": "bs"
        })
        
        # Submit request for takeaways
        response2 = client.post("/submit", json={
            "url": "https://podcasts.apple.com/us/podcast/episode?id=123456",
            "summary_type": "ts"
        })
        
        # Verify different cache keys were used
        calls = mock_redis.get.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == "episode:apple:123456:bs"
        assert calls[1][0][0] == "episode:apple:123456:ts"

    @patch('redis_stream_client.redis_client')
    def test_cache_platform_isolation(self, mock_redis):
        """Test that different platforms are cached separately"""
        
        # Mock cache miss
        mock_redis.get.return_value = None
        
        # Submit Apple Podcasts request
        response1 = client.post("/submit", json={
            "url": "https://podcasts.apple.com/us/podcast/episode?id=123456",
            "summary_type": "ts"
        })
        
        # Submit Spotify request (same episode ID)
        response2 = client.post("/submit", json={
            "url": "https://open.spotify.com/episode/123456",
            "summary_type": "ts"
        })
        
        # Verify different cache keys were used
        calls = mock_redis.get.call_args_list
        assert len(calls) == 2
        assert calls[0][0][0] == "episode:apple:123456:ts"
        assert calls[1][0][0] == "episode:spotify:123456:ts"

    @patch('redis_stream_client.redis_client')
    @patch('podcast_audio_resolver_service.get_audio.get_episode_audio_from_apple')
    @patch('podcast_audio_resolver_service.audio_upload_producer.emit_audio_uploaded')
    def test_cache_ttl_verification(self, mock_redis, mock_get_audio, mock_emit):
        """Test that cache entries are stored with correct TTL"""
        
        # Mock cache miss
        mock_redis.get.return_value = None
        
        # Mock successful audio extraction
        mock_get_audio.return_value = {
            "file_path": "audio_files/test.mp3",
            "metadata": {"title": "Test Episode"}
        }
        
        # Submit request
        response = client.post("/submit", json={
            "url": "https://podcasts.apple.com/us/podcast/episode?id=123456",
            "summary_type": "ts"
        })
        
        # Verify TTL was set correctly
        mock_redis.setex.assert_called()
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == CacheService.EPISODE_CACHE_TTL  # TTL value

    @patch('redis_stream_client.redis_client')
    @patch('podcast_audio_resolver_service.get_audio.get_episode_audio_from_apple')
    @patch('podcast_audio_resolver_service.audio_upload_producer.emit_audio_uploaded')
    def test_cache_data_structure_verification(self, mock_redis, mock_get_audio, mock_emit):
        """Test that cached data has the correct structure"""
        
        # Mock cache miss
        mock_redis.get.return_value = None
        
        # Mock successful audio extraction
        mock_get_audio.return_value = {
            "file_path": "audio_files/test.mp3",
            "metadata": {"title": "Test Episode"}
        }
        
        # Submit request
        response = client.post("/submit", json={
            "url": "https://podcasts.apple.com/us/podcast/episode?id=123456",
            "summary_type": "ts"
        })
        
        # Verify data structure
        mock_redis.setex.assert_called()
        call_args = mock_redis.setex.call_args
        cached_data = json.loads(call_args[0][2])
        
        # Check required fields
        required_fields = ["cached_at", "cache_ttl"]
        for field in required_fields:
            assert field in cached_data
        
        # Check data types
        assert isinstance(cached_data["cached_at"], (int, float))
        assert isinstance(cached_data["cache_ttl"], int)
        assert cached_data["cache_ttl"] == CacheService.EPISODE_CACHE_TTL

    @patch('redis_stream_client.redis_client')
    def test_cache_error_handling(self, mock_redis):
        """Test that cache errors don't break the application"""
        
        # Mock Redis error
        mock_redis.get.side_effect = Exception("Redis connection error")
        
        # Submit request - should still work
        response = client.post("/submit", json={
            "url": "https://podcasts.apple.com/us/podcast/episode?id=123456",
            "summary_type": "ts"
        })
        
        # Should handle error gracefully and proceed with processing
        assert response.status_code == 200

    @patch('redis_stream_client.redis_client')
    def test_cache_stats_integration(self, mock_redis):
        """Test cache statistics integration"""
        
        # Mock cache keys for both episode and transcript caches
        episode_keys = [
            "episode:apple:123:ts",
            "episode:spotify:456:bs",
            "episode:apple:789:ns"
        ]
        transcript_keys = [
            "transcript:abc123:ts",
            "transcript:def456:bs"
        ]
        
        def mock_keys(pattern):
            if pattern == "episode:*":
                return episode_keys
            elif pattern == "transcript:*":
                return transcript_keys
            return []
        
        mock_redis.keys.side_effect = mock_keys
        
        # Get cache stats
        response = client.get("/cache/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert data["episode_cache_count"] == 3
        assert data["transcript_cache_count"] == 2
        assert data["total_cached_items"] == 5

    @patch('redis_stream_client.redis_client')
    def test_cache_invalidation_integration(self, mock_redis):
        """Test cache invalidation integration"""
        
        # Mock successful invalidation
        mock_redis.delete.return_value = 1
        
        # Invalidate specific episode
        response = client.delete("/cache/invalidate/apple/123456/ts")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        # Verify correct key was deleted
        mock_redis.delete.assert_called_once_with("episode:apple:123456:ts")

    @patch('redis_stream_client.redis_client')
    def test_cache_clear_admin_integration(self, mock_redis):
        """Test admin cache clear integration"""
        
        # Mock cache keys for both episode and transcript caches
        episode_keys = ["episode:apple:123:ts", "episode:spotify:456:bs"]
        transcript_keys = ["transcript:abc123:ts", "transcript:def456:bs"]
        
        def mock_keys(pattern):
            if pattern == "episode:*":
                return episode_keys
            elif pattern == "transcript:*":
                return transcript_keys
            return []
        
        mock_redis.keys.side_effect = mock_keys
        mock_redis.delete.return_value = 1
        
        # Clear cache with admin key
        response = client.delete("/cache/clear?admin_key=default-admin-key")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        # Verify both episode and transcript keys were checked and deleted
        assert mock_redis.keys.call_count == 2
        assert mock_redis.delete.call_count == 2

    def test_cache_key_generation_consistency(self):
        """Test that cache keys are generated consistently"""
        
        # Test Apple Podcasts
        key1 = CacheService._generate_episode_key("apple", "123456", "ts")
        key2 = CacheService._generate_episode_key("apple", "123456", "ts")
        assert key1 == key2
        assert key1 == "episode:apple:123456:ts"
        
        # Test Spotify
        key3 = CacheService._generate_episode_key("spotify", "abc123", "bs")
        assert key3 == "episode:spotify:abc123:bs"
        
        # Test different summary types
        key4 = CacheService._generate_episode_key("apple", "123456", "ns")
        assert key4 == "episode:apple:123456:ns"
        assert key4 != key1  # Different summary type = different key

    def test_episode_id_extraction_consistency(self):
        """Test that episode ID extraction is consistent"""
        
        # Apple Podcasts
        url1 = "https://podcasts.apple.com/us/podcast/episode?id=123456&other=param"
        url2 = "https://podcasts.apple.com/us/podcast/episode?id=123456"
        
        id1 = CacheService.extract_episode_id(url1)
        id2 = CacheService.extract_episode_id(url2)
        
        assert id1 == id2
        assert id1 == "123456"
        
        # Spotify
        url3 = "https://open.spotify.com/episode/abc123?si=xyz"
        url4 = "https://open.spotify.com/episode/abc123"
        
        id3 = CacheService.extract_episode_id(url3)
        id4 = CacheService.extract_episode_id(url4)
        
        assert id3 == id4
        assert id3 == "abc123"

    @patch('redis_stream_client.redis_client')
    def test_cache_performance_verification(self, mock_redis):
        """Test that cache operations are fast"""
        
        import time
        
        # Mock fast Redis response
        mock_redis.get.return_value = json.dumps({"summary": "test"})
        
        # Measure cache hit time
        start_time = time.time()
        result = CacheService.get_cached_episode("apple", "123456", "ts")
        end_time = time.time()
        
        # Should be very fast (< 10ms)
        assert (end_time - start_time) < 0.01
        assert result is not None

    @patch('redis_stream_client.redis_client')
    def test_transcript_cache_integration(self, mock_redis):
        """Test transcript cache integration"""
        
        # Mock transcript cache miss then hit
        mock_redis.get.side_effect = [None, json.dumps({"summary": "Cached transcript summary"})]
        
        # Test transcript cache miss
        transcript = "This is a test transcript content"
        summary_type = "ts"
        
        result1 = CacheService.get_cached_transcript(transcript, summary_type)
        assert result1 is None
        
        # Test transcript cache hit
        result2 = CacheService.get_cached_transcript(transcript, summary_type)
        assert result2 is not None
        assert result2["summary"] == "Cached transcript summary"
        
        # Verify correct keys were used
        expected_key = f"transcript:{CacheService._generate_transcript_hash(transcript)}:{summary_type}"
        assert mock_redis.get.call_count == 2
        assert mock_redis.get.call_args_list[0][0][0] == expected_key
        assert mock_redis.get.call_args_list[1][0][0] == expected_key 