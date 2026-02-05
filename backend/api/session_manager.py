"""
Session Manager - handles multiple concurrent orchestrator sessions.

Each browser tab maps to a session. A single WebSocket connection
can have multiple sessions running simultaneously. Sessions are
identified by a short string ID.

Sessions track:
- The orchestrator instance
- Active project info
- Status (idle/working)
- Creation time
"""

import time
import uuid
from typing import Optional, Callable, Any
from dataclasses import dataclass, field

from ..orchestrator import ConversationalOrchestrator
from ..storage import Database


# Max sessions per WebSocket connection
MAX_SESSIONS_PER_CONNECTION = 10


@dataclass
class Session:
    """A single orchestrator session (one tab)."""
    id: str
    orchestrator: ConversationalOrchestrator
    status: str = "idle"  # idle, working
    project_name: Optional[str] = None
    project_id: Optional[int] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "project_name": self.project_name,
            "project_id": self.project_id,
            "created_at": self.created_at,
        }


class SessionManager:
    """Manages multiple orchestrator sessions for a single WebSocket connection."""

    def __init__(self, db: Database, projects_dir: str = "./projects"):
        self.db = db
        self.projects_dir = projects_dir
        self.sessions: dict[str, Session] = {}

    def create_session(self, on_event: Optional[Callable] = None) -> Session:
        """Create a new session and return it."""
        if len(self.sessions) >= MAX_SESSIONS_PER_CONNECTION:
            raise ValueError(f"Maximum {MAX_SESSIONS_PER_CONNECTION} sessions reached")

        session_id = uuid.uuid4().hex[:8]

        orchestrator = ConversationalOrchestrator(
            projects_dir=self.projects_dir,
            on_event=on_event,
            db=self.db,
        )

        session = Session(
            id=session_id,
            orchestrator=orchestrator,
        )
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        return self.sessions.get(session_id)

    def close_session(self, session_id: str) -> bool:
        """Close and clean up a session."""
        session = self.sessions.pop(session_id, None)
        if session:
            session.orchestrator.clear()
            return True
        return False

    def list_sessions(self) -> list[dict]:
        """List all sessions with their info."""
        result = []
        for session in self.sessions.values():
            info = session.to_dict()
            # Pull live project info from orchestrator state
            orch = session.orchestrator
            if orch.state.active_project_name:
                info["project_name"] = orch.state.active_project_name
                info["project_id"] = orch.state.active_project_id
            result.append(info)
        return result

    def set_status(self, session_id: str, status: str):
        """Update a session's status."""
        session = self.sessions.get(session_id)
        if session:
            session.status = status

    def cleanup_all(self):
        """Close all sessions."""
        for session_id in list(self.sessions.keys()):
            self.close_session(session_id)
