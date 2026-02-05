"""
SQLite database for project persistence.

Stores projects, sessions, and conversation memory in
~/.vibe-agents/vibe-agents.db. No external database dependency.

Tables:
- projects: Project metadata (name, description, directory, status)
- sessions: Agent session IDs for CLI persistence
- memory: Key-value store for project decisions and context
"""

import sqlite3
import json
import os
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from contextlib import contextmanager


# Default database location
DEFAULT_DB_DIR = Path.home() / ".vibe-agents"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "vibe-agents.db"


@dataclass
class Project:
    """A saved project."""
    id: Optional[int] = None
    name: str = ""
    description: str = ""
    directory: str = ""
    status: str = "active"  # active, archived, deleted
    created_at: float = 0.0
    updated_at: float = 0.0
    plan_json: str = ""
    file_count: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.plan_json:
            try:
                d["plan"] = json.loads(self.plan_json)
            except json.JSONDecodeError:
                d["plan"] = None
        else:
            d["plan"] = None
        del d["plan_json"]
        return d


@dataclass
class Session:
    """An agent's CLI session ID for a project."""
    id: Optional[int] = None
    project_id: int = 0
    agent_name: str = ""
    session_id: str = ""
    updated_at: float = 0.0


class Database:
    """SQLite persistence layer for Vibe Agents."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
            self.db_path = str(DEFAULT_DB_PATH)
        else:
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
            self.db_path = db_path

        self._init_db()

    @contextmanager
    def _connect(self):
        """Get a database connection with WAL mode for concurrency."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Create tables if they don't exist."""
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    directory TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    plan_json TEXT DEFAULT '',
                    file_count INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    agent_name TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    UNIQUE(project_id, agent_name)
                );

                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    UNIQUE(project_id, key)
                );

                CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
                CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at);
                CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id);
                CREATE INDEX IF NOT EXISTS idx_memory_project ON memory(project_id);
            """)

    # ==================== Projects ====================

    def create_project(self, name: str, directory: str,
                       description: str = "", plan: Optional[dict] = None) -> Project:
        """Create a new project."""
        now = time.time()
        plan_json = json.dumps(plan) if plan else ""

        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO projects (name, description, directory, status,
                   created_at, updated_at, plan_json, file_count)
                   VALUES (?, ?, ?, 'active', ?, ?, ?, 0)""",
                (name, description, directory, now, now, plan_json)
            )
            project_id = cursor.lastrowid

        return Project(
            id=project_id, name=name, description=description,
            directory=directory, status="active",
            created_at=now, updated_at=now,
            plan_json=plan_json, file_count=0
        )

    def get_project(self, project_id: int) -> Optional[Project]:
        """Get a project by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ? AND status != 'deleted'",
                (project_id,)
            ).fetchone()

        if not row:
            return None
        return self._row_to_project(row)

    def get_project_by_name(self, name: str) -> Optional[Project]:
        """Get a project by name."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE name = ? AND status != 'deleted' ORDER BY updated_at DESC LIMIT 1",
                (name,)
            ).fetchone()

        if not row:
            return None
        return self._row_to_project(row)

    def list_projects(self, status: str = "active", limit: int = 50) -> list[Project]:
        """List projects, most recently updated first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM projects WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
                (status, limit)
            ).fetchall()

        return [self._row_to_project(r) for r in rows]

    def update_project(self, project_id: int, **kwargs) -> bool:
        """Update project fields."""
        allowed = {"name", "description", "status", "plan_json", "file_count"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False

        updates["updated_at"] = time.time()

        # Handle plan dict -> json
        if "plan" in kwargs and "plan_json" not in kwargs:
            updates["plan_json"] = json.dumps(kwargs["plan"]) if kwargs["plan"] else ""

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [project_id]

        with self._connect() as conn:
            conn.execute(
                f"UPDATE projects SET {set_clause} WHERE id = ?",
                values
            )
        return True

    def delete_project(self, project_id: int) -> bool:
        """Soft-delete a project."""
        return self.update_project(project_id, status="deleted")

    def touch_project(self, project_id: int, file_count: Optional[int] = None):
        """Update the project's updated_at timestamp and optionally file count."""
        with self._connect() as conn:
            if file_count is not None:
                conn.execute(
                    "UPDATE projects SET updated_at = ?, file_count = ? WHERE id = ?",
                    (time.time(), file_count, project_id)
                )
            else:
                conn.execute(
                    "UPDATE projects SET updated_at = ? WHERE id = ?",
                    (time.time(), project_id)
                )

    # ==================== Sessions ====================

    def get_session(self, project_id: int, agent_name: str) -> Optional[str]:
        """Get the CLI session ID for an agent in a project."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT session_id FROM sessions WHERE project_id = ? AND agent_name = ?",
                (project_id, agent_name)
            ).fetchone()

        return row["session_id"] if row else None

    def save_session(self, project_id: int, agent_name: str, session_id: str):
        """Save or update a CLI session ID."""
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO sessions (project_id, agent_name, session_id, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(project_id, agent_name)
                   DO UPDATE SET session_id = excluded.session_id, updated_at = excluded.updated_at""",
                (project_id, agent_name, session_id, now)
            )

    def get_all_sessions(self, project_id: int) -> dict[str, str]:
        """Get all agent session IDs for a project."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT agent_name, session_id FROM sessions WHERE project_id = ?",
                (project_id,)
            ).fetchall()

        return {row["agent_name"]: row["session_id"] for row in rows}

    # ==================== Memory ====================

    def set_memory(self, project_id: int, key: str, value: str):
        """Store a key-value pair for a project."""
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO memory (project_id, key, value, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(project_id, key)
                   DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
                (project_id, key, value, now)
            )

    def get_memory(self, project_id: int, key: str) -> Optional[str]:
        """Get a stored value for a project."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM memory WHERE project_id = ? AND key = ?",
                (project_id, key)
            ).fetchone()

        return row["value"] if row else None

    def get_all_memory(self, project_id: int) -> dict[str, str]:
        """Get all stored key-value pairs for a project."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key, value FROM memory WHERE project_id = ?",
                (project_id,)
            ).fetchall()

        return {row["key"]: row["value"] for row in rows}

    # ==================== Helpers ====================

    def _row_to_project(self, row: sqlite3.Row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            directory=row["directory"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            plan_json=row["plan_json"],
            file_count=row["file_count"]
        )
