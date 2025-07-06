#!/usr/bin/env python3
"""
Test script to demonstrate the three-layer caching system:
1. Episode cache (platform + episode ID + summary type)
2. Local file cache (audio URL to local file mapping)
3. Transcript cache (file hash to transcript mapping)
"""

import os
import sys
import time
import json
from pathlib import Path

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from cache_service import CacheService
from podcast_audio_resolver_service.audio_extractor import load_download_cache, save_download_cache
from redis_stream_client import redis_client
# from transcription_service.audio_upload_consumer import AudioUploadConsumer

def test_three_layer_caching():
    """Test the complete three-layer caching system"""
    
    print("🧪 Testing Three-Layer Caching System")
    print("=" * 50)
    
    # Initialize cache service
    cache_service = CacheService()
    
    # Test data
    platform = "apple"
    episode_id = "test_episode_123"
    summary_type = "bullet_points"
    episode_title = "Test Episode"
    audio_url = "https://example.com/test_audio.mp3"
    
    print(f"\n📋 Test Parameters:")
    print(f"   Platform: {platform}")
    print(f"   Episode ID: {episode_id}")
    print(f"   Summary Type: {summary_type}")
    print(f"   Episode Title: {episode_title}")
    print(f"   Audio URL: {audio_url}")
    
    # Layer 1: Episode Cache Check
    print(f"\n🔍 Layer 1: Episode Cache Check")
    print("-" * 30)
    
    episode_cache_key = f"{platform}:{episode_id}:{summary_type}"
    cached_summary = cache_service.get_cached_episode(platform, episode_id, summary_type)
    
    if cached_summary:
        print(f"✅ Episode cache HIT - Summary found!")
        print(f"   Cache key: {episode_cache_key}")
        return "Episode cache hit - no further processing needed"
    else:
        print(f"❌ Episode cache MISS - Proceeding to Layer 2")
    
    # Layer 2: Local File Cache Check
    print(f"\n🔍 Layer 2: Local File Cache Check")
    print("-" * 30)
    
    # Load download cache
    download_cache = load_download_cache()
    clean_url = audio_url.split('?')[0]
    
    if clean_url in download_cache:
        cached_file_info = download_cache[clean_url]
        cached_file_path = cached_file_info["file_path"]
        cached_file_hash = cached_file_info["file_hash"]
        
        if os.path.exists(cached_file_path):
            print(f"✅ Local file cache HIT!")
            print(f"   File path: {cached_file_path}")
            print(f"   File hash: {cached_file_hash[:8]}...")
            file_path = cached_file_path
            file_hash = cached_file_hash
        else:
            print(f"⚠️ Cached file not found, removing from cache")
            del download_cache[clean_url]
            save_download_cache(download_cache)
            file_path = None
            file_hash = None
    else:
        print(f"❌ Local file cache MISS - File not downloaded yet")
        file_path = None
        file_hash = None
    
    if not file_path:
        print(f"📥 Would download audio file here...")
        # Simulate download
        file_path = f"audio_files/{episode_title.replace(' ', '_')}.mp3"
        file_hash = "simulated_hash_123"
        print(f"   Simulated file path: {file_path}")
        print(f"   Simulated file hash: {file_hash}")
    
    # Layer 3: Transcript Cache Check
    print(f"\n🔍 Layer 3: Transcript Cache Check")
    print("-" * 30)
    
    cached_transcript = cache_service.get_cached_transcript_by_hash(file_hash)
    
    if cached_transcript:
        print(f"✅ Transcript cache HIT!")
        print(f"   File hash: {file_hash[:8]}...")
        print(f"   Transcript length: {len(cached_transcript)} characters")
        transcript = cached_transcript
    else:
        print(f"❌ Transcript cache MISS - Would transcribe here...")
        # Simulate transcription
        transcript = f"Simulated transcript for {episode_title}..."
        print(f"   Simulated transcript: {transcript[:50]}...")
    
    # Simulate summary generation
    print(f"\n🤖 Summary Generation")
    print("-" * 30)
    
    summary = f"Simulated {summary_type} summary for {episode_title}"
    print(f"   Generated summary: {summary}")
    
    # Cache the results
    print(f"\n💾 Caching Results")
    print("-" * 30)
    
    # Cache transcript
    transcript_data = {
        "transcript": transcript,
        "metadata": {"episode_title": episode_title},
        "file_path": file_path,
        "file_hash": file_hash,
        "summaries": {summary_type: summary},
        "transcript_length": len(transcript)
    }
    cache_service.set_cached_transcript_by_hash(file_hash, transcript_data)
    print(f"   ✅ Cached transcript for hash: {file_hash[:8]}...")
    
    # Cache episode summary
    episode_data = {
        "summary": summary,
        "metadata": {"episode_title": episode_title},
        "summary_type": summary_type,
        "transcript_length": len(transcript),
        "file_path": file_path
    }
    cache_service.set_cached_episode(platform, episode_id, summary_type, episode_data)
    print(f"   ✅ Cached episode summary for key: {episode_cache_key}")
    
    # Cache local file info (if not already cached)
    if clean_url not in download_cache:
        download_cache[clean_url] = {
            "file_path": file_path,
            "file_hash": file_hash,
            "episode_title": episode_title
        }
        save_download_cache(download_cache)
        print(f"   ✅ Cached local file info for URL: {clean_url}")
    
    print(f"\n🎉 Three-layer caching test completed!")
    return "All layers processed successfully"

def show_cache_status():
    """Show current status of all cache layers"""
    
    print(f"\n📊 Cache Status Report")
    print("=" * 50)
    
    # Episode cache status
    episode_keys = redis_client.keys("episode:*")
    print(f"📋 Episode Cache: {len(episode_keys)} entries")
    for key in episode_keys[:3]:  # Show first 3
        if isinstance(key, bytes):
            print(f"   - {key.decode()}")
        else:
            print(f"   - {key}")
    if len(episode_keys) > 3:
        print(f"   ... and {len(episode_keys) - 3} more")
    
    # Local file cache status
    download_cache = load_download_cache()
    print(f"\n📁 Local File Cache: {len(download_cache)} entries")
    for url, info in list(download_cache.items())[:3]:  # Show first 3
        file_exists = "✅" if os.path.exists(info["file_path"]) else "❌"
        print(f"   {file_exists} {url[:50]}... -> {info['file_path']}")
    if len(download_cache) > 3:
        print(f"   ... and {len(download_cache) - 3} more")
    
    # Transcript cache status
    transcript_keys = redis_client.keys("transcript:*")
    print(f"\n📝 Transcript Cache: {len(transcript_keys)} entries")
    for key in transcript_keys[:3]:  # Show first 3
        if isinstance(key, bytes):
            print(f"   - {key.decode()}")
        else:
            print(f"   - {key}")
    if len(transcript_keys) > 3:
        print(f"   ... and {len(transcript_keys) - 3} more")

if __name__ == "__main__":
    try:
        # Run the test
        result = test_three_layer_caching()
        print(f"\n✅ Test Result: {result}")
        
        # Show cache status
        show_cache_status()
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc() 