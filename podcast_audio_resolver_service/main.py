import os
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agent.cache_gate import request_invalidate
from agent.catalog import openapi_extras
from agent.errors import HUMAN_INTERNAL, AgentError
from agent.routes import router as agent_router
from agent.summarize import start_summarize

load_dotenv()

ENV = os.getenv("ENV", "dev")
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000" if ENV == "test" else None)

if not frontend_url and ENV != "test":
    raise RuntimeError("Missing FRONTEND_URL environment variable.")

# Create FastAPI app
app = FastAPI()
app.include_router(agent_router)

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
async def download_episode(
    request: PodcastRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    try:
        result = start_summarize(request.url, request.summary_type, idempotency_key=idempotency_key)
        return result.human_body
    except AgentError as exc:
        if exc.code in ("invalid_input", "unsupported_platform"):
            raise HTTPException(status_code=400, detail=exc.human_detail)
        if exc.code == "idempotency_conflict":
            return {
                "message": exc.human_detail,
                "error": True,
                "data": None,
                "cached": False,
            }
        return {
            "message": HUMAN_INTERNAL,
            "error": True,
            "data": None,
            "cached": False,
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Server Error] {e}")
        return {
            "message": HUMAN_INTERNAL,
            "error": True,
            "data": None,
            "cached": False,
        }

@app.get(
    "/cache/stats",
    operation_id="get_cache_stats",
    openapi_extra=openapi_extras("get_cache_stats"),
)
async def get_cache_stats():
    """Get cache statistics"""
    from cache_service import CacheService
    return CacheService.get_cache_stats()

@app.delete("/cache/clear")
async def clear_cache(admin_key: str | None = None):
    """Clear all episode cache. Legacy admin_key path. Agent calls use approval instead."""
    from cache_service import CacheService
    # Legacy shared secret. New agent routes do not read this value.
    expected_key = os.getenv("ADMIN_CACHE_KEY", "default-admin-key")

    if not admin_key or admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Admin access required")

    success = CacheService.clear_cache()
    return {"success": success, "message": "Cache cleared successfully"}

@app.delete(
    "/cache/invalidate/{platform}/{episode_id}/{summary_type}",
    operation_id="invalidate_episode_cache",
    openapi_extra=openapi_extras("invalidate_episode_cache"),
)
async def invalidate_episode_cache(platform: str, episode_id: str, summary_type: str):
    """Invalidate specific episode cache entry. Requires a live approval."""
    # Treat 'none' as empty for compatibility with tests
    if platform == 'none':
        platform = ''
    if episode_id == 'none':
        episode_id = ''
    if summary_type == 'none':
        summary_type = ''
    if not episode_id or not platform or not summary_type:
        return {"success": False, "message": f"Cache invalidated for {platform}:{episode_id}:{summary_type}"}

    pending = request_invalidate(platform, episode_id, summary_type)
    return JSONResponse(status_code=202, content=pending)

@app.delete("/cache/invalidate/{platform}/{episode_id}/{summary_type}/", include_in_schema=False)
async def invalidate_episode_cache_trailing_slash(platform: str, episode_id: str, summary_type: str):
    """Alternative route for cache invalidation with trailing slash"""
    return await invalidate_episode_cache(platform, episode_id, summary_type)
