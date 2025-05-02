from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from podcast_audio_resolver_service.get_audio import get_episode_audio_from_apple, get_episode_audio_from_spotify
from podcast_audio_resolver_service.audio_upload_producer import emit_audio_uploaded
from fastapi.middleware.cors import CORSMiddleware
import uuid
import os
from dotenv import load_dotenv

load_dotenv()

frontend_url = os.getenv("FRONTEND_URL")

app = FastAPI()

origins = [
    frontend_url,   # React dev server
    # you can also add production URLs here, e.g. "https://app.echobrief.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,            # <-- your frontend origin(s)
    allow_credentials=True,           # <-- if you need to send cookies/auth headers
    allow_methods=["*"],              # <-- which HTTP methods are allowed
    allow_headers=["*"],              # <-- which headers are allowed
)

class PodcastRequest(BaseModel):
    url: str
    summary_type: str # ts, ns, bs

@app.post("/api/submit")
async def download_episode(request: PodcastRequest):
    url = request.url

    try:
        if "podcasts.apple.com" in url:
            data = get_episode_audio_from_apple(url)
        elif "open.spotify.com" in url:
            data = get_episode_audio_from_spotify(url)
        else:
            raise HTTPException(status_code=400, detail="Unsupported podcast platform")
        
        data['summary_type'] = request.summary_type
        data['job_id'] = str(uuid.uuid4())
        
        print(data)
        
        if data['file_path']:
            emit_audio_uploaded(data)
        else:
            return {
                "message": "No Episode Found"
            }


        return {
            "message": "Download successful",
            "data": data
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
