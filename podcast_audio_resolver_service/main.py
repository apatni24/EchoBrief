import os
import uuid
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from podcast_audio_resolver_service.get_audio import (
    get_episode_audio_from_apple,
    get_episode_audio_from_spotify
)
from podcast_audio_resolver_service.audio_upload_producer import emit_audio_uploaded

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

        if "podcasts.apple.com" in url:
            data = get_episode_audio_from_apple(url)
        elif "open.spotify.com" in url:
            data = get_episode_audio_from_spotify(url)
        else:
            raise HTTPException(status_code=400, detail="Unsupported podcast platform")

        if "error" in data:
            return {
                "message": data["error"],
                "error": True
            }

        # Enrich with metadata
        data["summary_type"] = summary_type
        data["job_id"] = str(uuid.uuid4())

        if data.get("file_path"):
            emit_audio_uploaded(data)
        else:
            return {
                "message": "No episode found or file path missing.",
                "error": True
            }

        return {
            "message": "Download successful",
            "data": data,
            "error": False
        }

    except Exception as e:
        print(f"[Server Error] {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
