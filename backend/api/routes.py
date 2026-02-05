"""FastAPI routes for the vibe-agents platform.

Phase 4: Multi-session support via session_id multiplexing.
A single WebSocket connection can have multiple sessions (tabs),
each with its own orchestrator. All messages include session_id.

Security features:
- Input validation and sanitization
- Message size limits
- Rate limiting per connection
"""

from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel, Field, field_validator
import asyncio
import json
import time

from ..orchestrator import Orchestrator, ConversationalOrchestrator
from ..storage import Database
from .session_manager import SessionManager

router = APIRouter()

# Constants for input validation
MAX_MESSAGE_LENGTH = 10000  # 10KB max message
MAX_MESSAGES_PER_MINUTE = 20  # Rate limit

# Shared database instance (singleton)
_db = Database()


class BuildRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)

    @field_validator('prompt')
    @classmethod
    def sanitize_prompt(cls, v: str) -> str:
        v = v.replace('\x00', '')
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
        now = time.time()

        if websocket not in self.requests:
            self.requests[websocket] = []

        self.requests[websocket] = [
            t for t in self.requests[websocket]
            if now - t < self.window_seconds
        ]

        if len(self.requests[websocket]) >= self.max_requests:
            return False

        self.requests[websocket].append(now)
        return True

    def cleanup(self, websocket: WebSocket):
        if websocket in self.requests:
            del self.requests[websocket]


class ConnectionManager:
    """Manage WebSocket connections with multi-session support."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.managers: dict[WebSocket, SessionManager] = {}
        self.rate_limiter = RateLimiter(MAX_MESSAGES_PER_MINUTE, 60)

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.managers[websocket] = SessionManager(db=_db, projects_dir="./projects")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        mgr = self.managers.pop(websocket, None)
        if mgr:
            mgr.cleanup_all()
        self.rate_limiter.cleanup(websocket)

    def check_rate_limit(self, websocket: WebSocket) -> bool:
        return self.rate_limiter.is_allowed(websocket)

    def get_manager(self, websocket: WebSocket) -> SessionManager:
        return self.managers[websocket]


manager = ConnectionManager()


# ==================== REST: Project Management ====================

@router.get("/projects")
async def list_projects(status: str = "active", limit: int = 50):
    """List all projects, most recently updated first."""
    if limit < 1 or limit > 100:
        limit = 50
    projects = _db.list_projects(status=status, limit=limit)
    return {
        "projects": [p.to_dict() for p in projects],
        "total": len(projects)
    }


@router.get("/projects/{project_id}")
async def get_project(project_id: int):
    """Get project details by ID."""
    project = _db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail={
            "code": "PROJECT_NOT_FOUND",
            "message": f"Project {project_id} not found"
        })
    return {"project": project.to_dict()}


@router.post("/projects/{project_id}/resume")
async def resume_project_endpoint(project_id: int):
    """Resume a project (returns project info for the frontend to use via WebSocket)."""
    project = _db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail={
            "code": "PROJECT_NOT_FOUND",
            "message": f"Project {project_id} not found"
        })
    return {
        "success": True,
        "project": project.to_dict(),
        "message": f"Project '{project.name}' ready to resume. Send a 'resume' message via WebSocket."
    }


@router.delete("/projects/{project_id}")
async def delete_project(project_id: int):
    """Soft-delete a project."""
    project = _db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail={
            "code": "PROJECT_NOT_FOUND",
            "message": f"Project {project_id} not found"
        })
    _db.delete_project(project_id)
    return {"success": True, "message": f"Project '{project.name}' deleted"}


# ==================== Health ====================

@router.get("/health")
async def health_check():
    """Basic health check - fast, for load balancers and uptime monitors."""
    return {"status": "ok", "service": "vibe-agents"}


@router.get("/health/detailed")
async def health_check_detailed():
    """Detailed health check with system diagnostics."""
    from ..health import get_full_health
    return get_full_health()


# ==================== Input Validation ====================

def validate_message(message: str) -> tuple[bool, str]:
    """Validate and sanitize a message."""
    if not message:
        return False, "Empty message"

    if len(message) > MAX_MESSAGE_LENGTH:
        return False, f"Message too long (max {MAX_MESSAGE_LENGTH} characters)"

    message = message.replace('\x00', '')
    message = ' '.join(message.split()).strip()

    if not message:
        return False, "Message is empty after sanitization"

    return True, message


# ==================== WebSocket ====================

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint with multi-session support.

    All messages include a session_id field. If omitted on chat/build,
    the server uses the first available session or creates one.

    Message types:
    - {"type": "new_session"} → Creates a new session, returns session_id
    - {"type": "close_session", "session_id": "..."} → Closes a session
    - {"type": "list_sessions"} → Lists all active sessions
    - {"type": "chat", "session_id": "...", "message": "..."} → Chat in a session
    - {"type": "build", "session_id": "...", "prompt": "..."} → Build in a session
    - {"type": "resume", "session_id": "...", "project_id": N} → Resume project
    - {"type": "clear", "session_id": "..."} → Clear a session

    All events sent back include session_id so the frontend routes
    them to the correct tab.
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "chat")
            session_id = data.get("session_id")

            # ---- Session management messages ----

            if msg_type == "new_session":
                await handle_new_session(websocket)
                continue

            if msg_type == "close_session":
                await handle_close_session(websocket, session_id)
                continue

            if msg_type == "list_sessions":
                await handle_list_sessions(websocket)
                continue

            # ---- Messages that target a specific session ----

            # Auto-resolve session: use provided, or first available, or create new
            session_id = await resolve_session(websocket, session_id)
            if not session_id:
                await websocket.send_json({
                    "type": "error",
                    "data": "No session available"
                })
                continue

            # Rate limiting
            if msg_type in ("chat", "build"):
                if not manager.check_rate_limit(websocket):
                    await websocket.send_json({
                        "type": "error",
                        "session_id": session_id,
                        "data": "Rate limit exceeded. Please wait before sending more messages."
                    })
                    continue

            if msg_type == "chat":
                message = data.get("message", "")
                valid, result = validate_message(message)
                if valid:
                    await run_chat(result, websocket, session_id)
                else:
                    await websocket.send_json({
                        "type": "error",
                        "session_id": session_id,
                        "data": result
                    })

            elif msg_type == "build":
                prompt = data.get("prompt", "")
                valid, result = validate_message(prompt)
                if valid:
                    await run_build(result, websocket, session_id)
                else:
                    await websocket.send_json({
                        "type": "error",
                        "session_id": session_id,
                        "data": result
                    })

            elif msg_type == "resume":
                project_id = data.get("project_id")
                if project_id is not None:
                    await run_resume(int(project_id), websocket, session_id)
                else:
                    await websocket.send_json({
                        "type": "error",
                        "session_id": session_id,
                        "data": "Missing project_id for resume"
                    })

            elif msg_type == "clear":
                mgr = manager.get_manager(websocket)
                session = mgr.get_session(session_id)
                if session:
                    session.orchestrator.clear()
                await websocket.send_json({
                    "type": "cleared",
                    "session_id": session_id,
                    "data": {}
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ==================== Session Handlers ====================

async def handle_new_session(websocket: WebSocket):
    """Create a new session and send back the session_id."""
    mgr = manager.get_manager(websocket)
    try:
        # Create with a temporary no-op callback; real callback set on first use
        session = mgr.create_session(on_event=None)
        await websocket.send_json({
            "type": "session_created",
            "session_id": session.id,
            "data": session.to_dict()
        })
    except ValueError as e:
        await websocket.send_json({
            "type": "error",
            "data": str(e)
        })


async def handle_close_session(websocket: WebSocket, session_id: str):
    """Close a session."""
    if not session_id:
        await websocket.send_json({"type": "error", "data": "Missing session_id"})
        return

    mgr = manager.get_manager(websocket)
    closed = mgr.close_session(session_id)
    await websocket.send_json({
        "type": "session_closed",
        "session_id": session_id,
        "data": {"success": closed}
    })


async def handle_list_sessions(websocket: WebSocket):
    """List all active sessions."""
    mgr = manager.get_manager(websocket)
    sessions = mgr.list_sessions()
    await websocket.send_json({
        "type": "sessions_list",
        "data": {"sessions": sessions}
    })


async def resolve_session(websocket: WebSocket, session_id: Optional[str] = None) -> Optional[str]:
    """Resolve a session_id: use provided, or first available, or auto-create."""
    mgr = manager.get_manager(websocket)

    # If session_id is provided and exists, use it
    if session_id and mgr.get_session(session_id):
        return session_id

    # If there are existing sessions, use the first one
    existing = mgr.list_sessions()
    if existing:
        return existing[0]["id"]

    # Auto-create a session
    try:
        session = mgr.create_session(on_event=None)
        await websocket.send_json({
            "type": "session_created",
            "session_id": session.id,
            "data": session.to_dict()
        })
        return session.id
    except ValueError:
        return None


# ==================== Action Handlers ====================

def _make_event_sender(websocket: WebSocket, session_id: str, loop):
    """Create an event sender that tags all events with session_id."""

    async def send_event(event_type: str, data):
        try:
            if isinstance(data, dict):
                serializable = data
            elif isinstance(data, str):
                serializable = data
            else:
                serializable = str(data)

            await websocket.send_json({
                "type": event_type,
                "session_id": session_id,
                "data": serializable
            })
        except Exception:
            pass

    def on_event(event_type: str, data):
        asyncio.run_coroutine_threadsafe(send_event(event_type, data), loop)

    return send_event, on_event


async def run_chat(message: str, websocket: WebSocket, session_id: str):
    """Handle a chat message in a specific session."""
    loop = asyncio.get_event_loop()
    send_event, on_event = _make_event_sender(websocket, session_id, loop)

    mgr = manager.get_manager(websocket)
    session = mgr.get_session(session_id)
    if not session:
        await send_event("error", "Session not found")
        return

    # Update event callback and status
    session.orchestrator.on_event = on_event
    mgr.set_status(session_id, "working")

    result = await loop.run_in_executor(None, session.orchestrator.chat, message)

    mgr.set_status(session_id, "idle")
    await send_event("chat_response", result)


async def run_build(prompt: str, websocket: WebSocket, session_id: str):
    """Run the full build pipeline in a specific session."""
    loop = asyncio.get_event_loop()
    send_event, on_event = _make_event_sender(websocket, session_id, loop)

    mgr = manager.get_manager(websocket)
    session = mgr.get_session(session_id)
    if not session:
        await send_event("error", "Session not found")
        return

    session.orchestrator.on_event = on_event
    mgr.set_status(session_id, "working")

    # For build mode, use the pipeline orchestrator
    orchestrator = Orchestrator(
        projects_dir="./projects",
        on_event=on_event
    )

    result = await loop.run_in_executor(None, orchestrator.build, prompt)

    mgr.set_status(session_id, "idle")
    await send_event("build_complete", result)


async def run_resume(project_id: int, websocket: WebSocket, session_id: str):
    """Resume a previously saved project in a specific session."""
    loop = asyncio.get_event_loop()
    send_event, on_event = _make_event_sender(websocket, session_id, loop)

    mgr = manager.get_manager(websocket)
    session = mgr.get_session(session_id)
    if not session:
        await send_event("error", "Session not found")
        return

    session.orchestrator.on_event = on_event
    mgr.set_status(session_id, "working")

    result = await loop.run_in_executor(
        None, session.orchestrator.resume_project, project_id
    )

    mgr.set_status(session_id, "idle")

    if result.get("error"):
        await send_event("error", result["error"])
    else:
        await send_event("project_resumed", result)
