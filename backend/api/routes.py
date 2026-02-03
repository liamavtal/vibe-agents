"""FastAPI routes for the vibe-agents platform.

Two modes:
1. Chat mode (new) - Conversational interface with smart agent routing
2. Build mode (legacy) - Full pipeline for complete project builds

Security features:
- Input validation and sanitization
- Message size limits
- Rate limiting per connection
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator
import asyncio
import json
import re
import time

from ..orchestrator import Orchestrator, ConversationalOrchestrator

router = APIRouter()

# Constants for input validation
MAX_MESSAGE_LENGTH = 10000  # 10KB max message
MAX_MESSAGES_PER_MINUTE = 20  # Rate limit


class BuildRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)

    @field_validator('prompt')
    @classmethod
    def sanitize_prompt(cls, v: str) -> str:
        # Remove null bytes and other problematic characters
        v = v.replace('\x00', '')
        # Normalize whitespace
        v = ' '.join(v.split())
        return v.strip()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)

    @field_validator('message')
    @classmethod
    def sanitize_message(cls, v: str) -> str:
        v = v.replace('\x00', '')
        v = ' '.join(v.split())
        return v.strip()


class RateLimiter:
    """Simple rate limiter per connection."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[WebSocket, list[float]] = {}

    def is_allowed(self, websocket: WebSocket) -> bool:
        """Check if request is allowed under rate limit."""
        now = time.time()

        if websocket not in self.requests:
            self.requests[websocket] = []

        # Clean old requests outside the window
        self.requests[websocket] = [
            t for t in self.requests[websocket]
            if now - t < self.window_seconds
        ]

        # Check if under limit
        if len(self.requests[websocket]) >= self.max_requests:
            return False

        # Record this request
        self.requests[websocket].append(now)
        return True

    def cleanup(self, websocket: WebSocket):
        """Clean up when connection closes."""
        if websocket in self.requests:
            del self.requests[websocket]


class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        # Store conversational orchestrators per connection for session persistence
        self.sessions: dict[WebSocket, ConversationalOrchestrator] = {}
        # Rate limiter: 20 requests per minute
        self.rate_limiter = RateLimiter(MAX_MESSAGES_PER_MINUTE, 60)

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.sessions:
            del self.sessions[websocket]
        self.rate_limiter.cleanup(websocket)

    def check_rate_limit(self, websocket: WebSocket) -> bool:
        """Check if request is within rate limit."""
        return self.rate_limiter.is_allowed(websocket)

    def get_session(self, websocket: WebSocket, on_event) -> ConversationalOrchestrator:
        """Get or create a conversational session for this connection."""
        if websocket not in self.sessions:
            self.sessions[websocket] = ConversationalOrchestrator(
                projects_dir="./projects",
                on_event=on_event
            )
        return self.sessions[websocket]

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


def validate_message(message: str) -> tuple[bool, str]:
    """Validate and sanitize a message."""
    if not message:
        return False, "Empty message"

    if len(message) > MAX_MESSAGE_LENGTH:
        return False, f"Message too long (max {MAX_MESSAGE_LENGTH} characters)"

    # Remove null bytes and normalize whitespace
    message = message.replace('\x00', '')
    message = ' '.join(message.split()).strip()

    if not message:
        return False, "Message is empty after sanitization"

    return True, message


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time agent updates.

    Supports two message types:
    - {"type": "chat", "message": "..."} - Conversational mode (smart routing)
    - {"type": "build", "prompt": "..."} - Full build pipeline mode

    Chat mode is the new default - it works like Claude Code.
    Build mode is for explicit full-project builds.
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "chat")

            # Rate limiting
            if msg_type in ("chat", "build"):
                if not manager.check_rate_limit(websocket):
                    await websocket.send_json({
                        "type": "error",
                        "data": "Rate limit exceeded. Please wait before sending more messages."
                    })
                    continue

            if msg_type == "chat":
                # Conversational mode - smart agent routing
                message = data.get("message", "")
                valid, result = validate_message(message)
                if valid:
                    await run_chat(result, websocket)
                else:
                    await websocket.send_json({"type": "error", "data": result})

            elif msg_type == "build":
                # Legacy mode - full pipeline
                prompt = data.get("prompt", "")
                valid, result = validate_message(prompt)
                if valid:
                    await run_build(result, websocket)
                else:
                    await websocket.send_json({"type": "error", "data": result})

            elif msg_type == "clear":
                # Clear conversation and project state
                if websocket in manager.sessions:
                    manager.sessions[websocket].clear()
                await websocket.send_json({"type": "cleared", "data": {}})

    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def run_chat(message: str, websocket: WebSocket):
    """
    Handle a chat message with smart agent routing.

    This is the new conversational interface that works like Claude Code.
    """
    async def send_event(event_type: str, data):
        """Send event to the connected client."""
        try:
            await websocket.send_json({
                "type": event_type,
                "data": data
            })
        except Exception:
            pass

    def on_event(event_type: str, data):
        asyncio.create_task(send_event(event_type, data))

    # Get or create session for this connection
    orchestrator = manager.get_session(websocket, on_event)

    # Run chat (synchronous but sends updates via callback)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, orchestrator.chat, message)

    # Send final response
    await send_event("chat_response", result)


async def run_build(prompt: str, websocket: WebSocket):
    """Run the full build pipeline with real-time updates."""

    async def send_event(event_type: str, data):
        """Send event to the connected client."""
        try:
            await websocket.send_json({
                "type": event_type,
                "data": data
            })
        except Exception:
            pass

    def on_event(event_type: str, data):
        asyncio.create_task(send_event(event_type, data))

    orchestrator = Orchestrator(
        projects_dir="./projects",
        on_event=on_event
    )

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, orchestrator.build, prompt)

    await send_event("build_complete", result)
