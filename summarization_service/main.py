from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
from summarization_service import transcription_complete_consumer
from summarization_service.ws_manager import manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(transcription_complete_consumer.consume_transcription_completed())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)


@app.websocket("/ws/summary/{job_id}")
async def ws_summary(websocket: WebSocket, job_id: str):
    await websocket.accept()                           # Must accept the handshake :contentReference[oaicite:2]{index=2}
    await manager.connect(job_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(job_id, websocket)
    except Exception as e:
        print("Web Socket Error: ",e)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or ["*"] for wide-open during testing
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

@app.get("/health")
def health_check():
    return {"status": "summarization_service is running"}

