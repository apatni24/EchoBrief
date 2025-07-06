import os
import uuid
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import podcast_audio_resolver_service.get_audio as get_audio
import podcast_audio_resolver_service.audio_upload_producer as audio_upload_producer
from cache_service import CacheService

load_dotenv()

ENV = os.getenv("ENV", "dev")
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000" if ENV == "test" else None)

if not frontend_url and ENV != "test":
    raise RuntimeError("Missing FRONTEND_URL environment variable.")

# Create FastAPI app
app = FastAPI()

# CORS setup
origins = [frontend_url]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Request model
class PodcastRequest(BaseModel):
    url: str
    summary_type: str  # ts, ns, bs

# Route
@app.post("/submit")
async def download_episode(request: PodcastRequest):
    try:
        url = request.url.strip()
        summary_type = request.summary_type
        
        # Validate input
        if not url:
            raise HTTPException(status_code=400, detail="URL is required")
        
        if not summary_type or summary_type not in ['ts', 'ns', 'bs']:
            raise HTTPException(status_code=400, detail="Invalid summary type. Must be 'ts', 'ns', or 'bs'")
        
        # Extract platform and episode ID for caching
        platform = CacheService.get_platform(url)
        episode_id = CacheService.extract_episode_id(url)

        # Validate platform and episode_id
        if platform == "unknown" or not episode_id:
            raise HTTPException(status_code=400, detail="Unsupported podcast platform. Only Apple Podcasts and Spotify are supported.")
        
        # Check cache first
        cached_result = CacheService.get_cached_episode(platform, episode_id, summary_type)
        if cached_result:
            # For cache hits, ensure required fields but DO NOT include job_id (no WebSocket needed)
            if "platform" not in cached_result:
                cached_result["platform"] = platform
            if "episode_id" not in cached_result:
                cached_result["episode_id"] = episode_id
            if "summary_type" not in cached_result:
                cached_result["summary_type"] = summary_type
            
            return {
                "message": "Cached result retrieved",
                "data": cached_result,
                "error": False,
                "cached": True,
                "processing_time": 0
            }
        
        # If not cached, proceed with normal flow
        data = None
        if "podcasts.apple.com" in url:
            data = get_audio.get_episode_audio_from_apple(url)
        elif "open.spotify.com" in url:
            data = get_audio.get_episode_audio_from_spotify(url)
        else:
            raise HTTPException(status_code=400, detail="Unsupported podcast platform. Only Apple Podcasts and Spotify are supported.")

        # Handle errors from audio resolver
        if data is None:
            return {
                "message": "Failed to process podcast URL. Please check the URL and try again.",
                "error": True,
                "data": None,
                "cached": False
            }

        if "error" in data:
            return {
                "message": data["error"],
                "error": True,
                "data": None,
                "cached": False
            }

        # Validate required fields
        if not data.get("file_path"):
            return {
                "message": "Audio file not found or could not be downloaded.",
                "error": True,
                "data": None,
                "cached": False
            }

        if not data.get("metadata"):
            return {
                "message": "Episode metadata not found.",
                "error": True,
                "data": None,
                "cached": False
            }

        # Enrich with metadata
        data["summary_type"] = summary_type
        data["job_id"] = str(uuid.uuid4())
        data["platform"] = platform
        data["episode_id"] = episode_id

        # Emit event for processing
        try:
            audio_upload_producer.emit_audio_uploaded(data)
        except Exception as e:
            print(f"Error emitting audio_uploaded event: {e}")
            return {
                "message": "Failed to start processing. Please try again.",
                "error": True,
                "data": None,
                "cached": False
            }

        return {
            "message": "Download successful",
            "data": data,
            "error": False,
            "cached": False
        }

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        print(f"[Server Error] {e}")
        return {
            "message": "Internal server error. Please try again later.",
            "error": True,
            "data": None,
            "cached": False
        }

@app.get("/cache/stats")
async def get_cache_stats():
    """Get cache statistics"""
    return CacheService.get_cache_stats()

@app.delete("/cache/clear")
async def clear_cache(admin_key: str = None):
    """Clear all episode cache - requires admin authentication"""
    # Simple admin key check (in production, use proper authentication)
    expected_key = os.getenv("ADMIN_CACHE_KEY", "default-admin-key")
    
    if not admin_key or admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    success = CacheService.clear_cache()
    return {"success": success, "message": "Cache cleared successfully"}

@app.delete("/cache/invalidate/{platform}/{episode_id}/{summary_type}")
async def invalidate_episode_cache(platform: str, episode_id: str, summary_type: str):
    """Invalidate specific episode cache entry"""
    # Treat 'none' as empty for compatibility with tests
    if platform == 'none':
        platform = ''
    if episode_id == 'none':
        episode_id = ''
    if summary_type == 'none':
        summary_type = ''
    if not episode_id or not platform or not summary_type:
        return {"success": False, "message": f"Cache invalidated for {platform}:{episode_id}:{summary_type}"}
    
    success = CacheService.invalidate_specific_episode(platform, episode_id, summary_type)
    return {"success": success, "message": f"Cache invalidated for {platform}:{episode_id}:{summary_type}"}

@app.delete("/cache/invalidate/{platform}/{episode_id}/{summary_type}/")
async def invalidate_episode_cache_trailing_slash(platform: str, episode_id: str, summary_type: str):
    """Alternative route for cache invalidation with trailing slash"""
    return await invalidate_episode_cache(platform, episode_id, summary_type)
