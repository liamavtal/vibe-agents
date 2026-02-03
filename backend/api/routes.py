"""FastAPI routes for the vibe-agents platform."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import asyncio
import json

from ..orchestrator import Orchestrator

router = APIRouter()


class BuildRequest(BaseModel):
    prompt: str


class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "vibe-agents"}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time agent updates.

    Clients connect here to watch agents work in real-time.
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "build":
                prompt = data.get("prompt", "")
                if prompt:
                    # Run build in background, streaming updates
                    await run_build(prompt, websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def run_build(prompt: str, websocket: WebSocket):
    """Run the build process with real-time updates."""

    async def send_event(event_type: str, data):
        """Send event to the connected client."""
        try:
            await websocket.send_json({
                "type": event_type,
                "data": data
            })
        except Exception:
            pass

    # Create orchestrator with event callback
    def on_event(event_type: str, data):
        # Schedule the async send in the event loop
        asyncio.create_task(send_event(event_type, data))

    orchestrator = Orchestrator(
        projects_dir="./projects",
        on_event=on_event
    )

    # Run the build (this is synchronous but sends updates via callback)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, orchestrator.build, prompt)

    # Send final result
    await send_event("build_complete", result)
