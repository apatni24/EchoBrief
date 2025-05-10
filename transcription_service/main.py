# summarization_service/main.py  (or transcription_service/main.py)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio

from transcription_service.audio_upload_consumer import consume_audio_uploaded

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    # launch the blocking consumer in a thread, passing the loop
    asyncio.create_task(asyncio.to_thread(consume_audio_uploaded, loop))
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/health")
def health_check():
    return {"status": "transcription_service is running"}
