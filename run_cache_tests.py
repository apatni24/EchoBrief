#!/usr/bin/env python3
"""
Cache Implementation Test Runner
Runs all cache-related tests and provides a comprehensive report.
"""

import sys
import os
import subprocess
import time
from pathlib import Path

def run_command(command, description):
    """Run a command and return success status"""
    print(f"\n🔄 {description}...")
    print(f"Command: {command}")
    
    start_time = time.time()
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        end_time = time.time()
        
        if result.returncode == 0:
            print(f"✅ {description} completed successfully ({end_time - start_time:.2f}s)")
            if result.stdout:
                print("Output:")
                print(result.stdout)
            return True
        else:
            print(f"❌ {description} failed ({end_time - start_time:.2f}s)")
            print("Error:")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ {description} failed with exception: {e}")
        return False

def main():
    """Main test runner"""
    print("🧪 EchoBrief Cache Implementation Test Suite")
    print("=" * 50)
    
    # Change to backend directory
    backend_dir = Path(__file__).parent
    os.chdir(backend_dir)
    
    # Test results tracking
    test_results = []
    
    # 1. Run cache service unit tests
    success = run_command(
        "venv/bin/python -m pytest tests/test_cache_service.py -v",
        "Cache Service Unit Tests"
    )
    test_results.append(("Cache Service Unit Tests", success))
    
    # 2. Run cache endpoints tests
    success = run_command(
        "venv/bin/python -m pytest tests/test_cache_endpoints.py -v",
        "Cache Endpoints Tests"
    )
    test_results.append(("Cache Endpoints Tests", success))
    
    # 3. Run cache integration tests
    success = run_command(
        "venv/bin/python -m pytest tests/test_cache_integration.py -v",
        "Cache Integration Tests"
    )
    test_results.append(("Cache Integration Tests", success))
    
    # 4. Run all cache tests together
    success = run_command(
        "venv/bin/python -m pytest tests/test_cache_*.py -v --tb=short",
        "All Cache Tests Combined"
    )
    test_results.append(("All Cache Tests Combined", success))
    
    # 5. Run with coverage
    success = run_command(
        "venv/bin/python -m pytest tests/test_cache_*.py --cov=cache_service --cov=podcast_audio_resolver_service --cov-report=term-missing",
        "Cache Tests with Coverage"
    )
    test_results.append(("Cache Tests with Coverage", success))
    
    # 6. Test cache service directly
    print("\n🧪 Testing Cache Service Directly...")
    try:
        from cache_service import CacheService
        
        # Test URL parsing
        apple_url = "https://podcasts.apple.com/us/podcast/episode?id=123456"
        spotify_url = "https://open.spotify.com/episode/abc123"
        
        assert CacheService.get_platform(apple_url) == "apple"
        assert CacheService.get_platform(spotify_url) == "spotify"
        assert CacheService.extract_episode_id(apple_url) == "123456"
        assert CacheService.extract_episode_id(spotify_url) == "abc123"
        
        # Test key generation
        key = CacheService._generate_episode_key("apple", "123456", "ts")
        assert key == "episode:apple:123456:ts"
        
        print("✅ Cache Service direct tests passed")
        test_results.append(("Cache Service Direct Tests", True))
        
    except Exception as e:
        print(f"❌ Cache Service direct tests failed: {e}")
        test_results.append(("Cache Service Direct Tests", False))
    
    # 7. Test API endpoints directly
    print("\n🧪 Testing API Endpoints Directly...")
    try:
        from fastapi.testclient import TestClient
        from podcast_audio_resolver_service.main import app
        
        client = TestClient(app)
        
        # Test cache stats endpoint
        response = client.get("/cache/stats")
        assert response.status_code == 200
        
        # Test cache clear without auth
        response = client.delete("/cache/clear")
        assert response.status_code == 403
        
        print("✅ API Endpoints direct tests passed")
        test_results.append(("API Endpoints Direct Tests", True))
        
    except Exception as e:
        print(f"❌ API Endpoints direct tests failed: {e}")
        test_results.append(("API Endpoints Direct Tests", False))
    
    # Print summary
    print("\n" + "=" * 50)
    print("📊 TEST SUMMARY")
    print("=" * 50)
    
    passed = 0
    total = len(test_results)
    
    for test_name, success in test_results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if success:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} test suites passed")
    
    if passed == total:
        print("🎉 All cache tests passed! Cache implementation is working correctly.")
        return 0
    else:
        print("⚠️ Some cache tests failed. Please review the implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 