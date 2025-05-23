from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio

from summarization_service.transcription_complete_consumer import consume_transcription_completed
from summarization_service.ws_manager import manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    # launch your blocking consumer in a thread, passing the loop
    asyncio.create_task(asyncio.to_thread(consume_transcription_completed, loop))
    yield

app = FastAPI(lifespan=lifespan)
# … routes, WebSocket endpoints, middleware, etc.



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

