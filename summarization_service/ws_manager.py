from fastapi import WebSocket, WebSocketDisconnect

class ConnectionManager:
    def __init__(self):
        # Map job_id -> list of WebSocket connections
        self.active: dict[str, list[WebSocket]] = {}

    async def connect(self, job_id: str, websocket: WebSocket):
        # await websocket.accept()
        self.active.setdefault(job_id, []).append(websocket)

    def disconnect(self, job_id: str, websocket: WebSocket):
        conns = self.active.get(job_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self.active.pop(job_id, None)

    async def broadcast(self, job_id: str, message: dict):
        # Send message JSON to all sockets listening on job_id
        conns = self.active.get(job_id, [])
        print(conns)
        for ws in list(conns):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(job_id, ws)

# instantiate a single manager for import
manager = ConnectionManager()