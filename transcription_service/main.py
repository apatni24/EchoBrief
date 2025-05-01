from fastapi import FastAPI
import asyncio
from transcription_service.audio_upload_consumer import consume_audio_uploaded
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background task
    task = asyncio.create_task(consume_audio_uploaded())

    yield  # app runs during this time

    # Optional: add cleanup logic here
    task.cancel()

app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health_check():
    return {"status": "transcription_service is running"}
