import os
import json
import hashlib
import time
import re
from typing import Optional, Dict, Any
from redis_stream_client import redis_client

class CacheService:
    """Multi-layer caching service for EchoBrief"""
    
    # Cache prefixes
    EPISODE_CACHE_PREFIX = "episode"
    TRANSCRIPT_CACHE_PREFIX = "transcript"
    
    # TTL values (in seconds) - 7 days
    EPISODE_CACHE_TTL = 7 * 24 * 60 * 60
    TRANSCRIPT_CACHE_TTL = 7 * 24 * 60 * 60
    
    @staticmethod
    def _generate_episode_key(platform: str, episode_id: str, summary_type: str) -> str:
        """Generate cache key for episode-level caching"""
        return f"{CacheService.EPISODE_CACHE_PREFIX}:{platform}:{episode_id}:{summary_type}"
    
    @staticmethod
    def extract_episode_id(url: str) -> str:
        """Extract episode ID from URL"""
        if "podcasts.apple.com" in url:
            # Extract from Apple URL: ?i=123456 or id=123456
            match = re.search(r'[?&]i=(\d+)', url)
            if not match:
                match = re.search(r'[?&]id=(\d+)', url)
            return match.group(1) if match else hashlib.md5(url.encode()).hexdigest()
        elif "open.spotify.com" in url:
            # Extract from Spotify URL: /episode/abc123
            match = re.search(r'/episode/([a-zA-Z0-9]+)', url)
            return match.group(1) if match else hashlib.md5(url.encode()).hexdigest()
        else:
            return hashlib.md5(url.encode()).hexdigest()
    
    @staticmethod
    def get_platform(url: str) -> str:
        """Get platform from URL"""
        if "podcasts.apple.com" in url:
            return "apple"
        elif "open.spotify.com" in url:
            return "spotify"
        else:
            return "unknown"
    
    @staticmethod
    def get_cached_episode(platform: str, episode_id: str, summary_type: str) -> Optional[Dict[str, Any]]:
        """Get cached episode summary"""
        try:
            key = CacheService._generate_episode_key(platform, episode_id, summary_type)
            cached_data = redis_client.get(key)
            
            if cached_data:
                data = json.loads(cached_data)
                print(f"🎯 Cache HIT: Found cached episode {episode_id} for {summary_type}")
                return data
            
            print(f"❌ Cache MISS: No cached episode {episode_id} for {summary_type}")
            return None
            
        except Exception as e:
            print(f"⚠️ Cache error: {e}")
            return None
    
    @staticmethod
    def set_cached_episode(platform: str, episode_id: str, summary_type: str, data: Dict[str, Any]) -> bool:
        """Cache episode summary"""
        try:
            key = CacheService._generate_episode_key(platform, episode_id, summary_type)
            cache_data = {
                **data,
                "cached_at": time.time(),
                "cache_ttl": CacheService.EPISODE_CACHE_TTL
            }
            
            redis_client.setex(
                key, 
                CacheService.EPISODE_CACHE_TTL, 
                json.dumps(cache_data)
            )
            
            print(f"💾 Cached episode {episode_id} for {summary_type}")
            return True
            
        except Exception as e:
            print(f"⚠️ Cache set error: {e}")
            return False
    
    @staticmethod
    def invalidate_specific_episode(platform: str, episode_id: str, summary_type: str) -> bool:
        """Invalidate a specific episode cache entry"""
        try:
            key = CacheService._generate_episode_key(platform, episode_id, summary_type)
            result = redis_client.delete(key)
            if result:
                print(f"🗑️ Invalidated cache for episode {episode_id} ({summary_type})")
            return bool(result)
        except Exception as e:
            print(f"⚠️ Cache invalidation error: {e}")
            return False
    
    @staticmethod
    def get_cache_stats() -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            # Count episode cache keys
            episode_keys = len(redis_client.keys(f"{CacheService.EPISODE_CACHE_PREFIX}:*"))
            transcript_keys = len(redis_client.keys(f"{CacheService.TRANSCRIPT_CACHE_PREFIX}:*"))
            
            return {
                "episode_cache_count": episode_keys,
                "transcript_cache_count": transcript_keys,
                "total_cached_items": episode_keys + transcript_keys
            }
            
        except Exception as e:
            print(f"⚠️ Cache stats error: {e}")
            return {"error": str(e)}
    
    @staticmethod
    def _generate_transcript_key(transcript_hash: str, summary_type: str) -> str:
        """Generate cache key for transcript-level caching"""
        return f"{CacheService.TRANSCRIPT_CACHE_PREFIX}:{transcript_hash}:{summary_type}"
    
    @staticmethod
    def _generate_transcript_hash(transcript: str) -> str:
        """Generate hash for transcript content"""
        return hashlib.sha256(transcript.encode('utf-8')).hexdigest()
    
    @staticmethod
    def get_cached_transcript(transcript: str, summary_type: str) -> Optional[Dict[str, Any]]:
        """Get cached transcript summary"""
        try:
            transcript_hash = CacheService._generate_transcript_hash(transcript)
            key = CacheService._generate_transcript_key(transcript_hash, summary_type)
            cached_data = redis_client.get(key)
            
            if cached_data:
                data = json.loads(cached_data)
                print(f"🎯 Transcript Cache HIT: Found cached transcript for {summary_type}")
                return data
            
            print(f"❌ Transcript Cache MISS: No cached transcript for {summary_type}")
            return None
            
        except Exception as e:
            print(f"⚠️ Transcript cache error: {e}")
            return None
    
    @staticmethod
    def set_cached_transcript(transcript: str, summary_type: str, data: Dict[str, Any]) -> bool:
        """Cache transcript summary"""
        try:
            transcript_hash = CacheService._generate_transcript_hash(transcript)
            key = CacheService._generate_transcript_key(transcript_hash, summary_type)
            cache_data = {
                **data,
                "cached_at": time.time(),
                "cache_ttl": CacheService.TRANSCRIPT_CACHE_TTL,
                "transcript_hash": transcript_hash
            }
            
            redis_client.setex(
                key, 
                CacheService.TRANSCRIPT_CACHE_TTL, 
                json.dumps(cache_data)
            )
            
            print(f"💾 Cached transcript for {summary_type}")
            return True
            
        except Exception as e:
            print(f"⚠️ Transcript cache set error: {e}")
            return False
    
    @staticmethod
    def invalidate_specific_transcript(transcript: str, summary_type: str) -> bool:
        """Invalidate a specific transcript cache entry"""
        try:
            transcript_hash = CacheService._generate_transcript_hash(transcript)
            key = CacheService._generate_transcript_key(transcript_hash, summary_type)
            result = redis_client.delete(key)
            if result:
                print(f"🗑️ Invalidated transcript cache for {summary_type}")
            return bool(result)
        except Exception as e:
            print(f"⚠️ Transcript cache invalidation error: {e}")
            return False
    
    @staticmethod
    def clear_cache() -> bool:
        """Clear all cache - ADMIN ONLY"""
        try:
            episode_keys = redis_client.keys(f"{CacheService.EPISODE_CACHE_PREFIX}:*")
            transcript_keys = redis_client.keys(f"{CacheService.TRANSCRIPT_CACHE_PREFIX}:*")
            
            total_cleared = 0
            if episode_keys:
                redis_client.delete(*episode_keys)
                total_cleared += len(episode_keys)
                print(f"🧹 Cleared {len(episode_keys)} cached episodes")
            
            if transcript_keys:
                redis_client.delete(*transcript_keys)
                total_cleared += len(transcript_keys)
                print(f"🧹 Cleared {len(transcript_keys)} cached transcripts")
            
            if total_cleared == 0:
                print("🧹 No cached items to clear")
            
            return True
            
        except Exception as e:
            print(f"⚠️ Cache clear error: {e}")
            return False 