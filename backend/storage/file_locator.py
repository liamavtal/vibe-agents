"""
Smart File Placement - decides where project files should go.

Logic:
1. If user mentions an existing project name → that project's directory
2. If there's an active project in the session → that project's directory
3. If "build me a new..." → create in projects/ with a new name
4. If quick snippet / no project context → scratch directory

Also handles creating project directories and updating the database.
"""

import os
import re
from pathlib import Path
from typing import Optional

from .database import Database, Project


class FileLocator:
    """Determines where files should be placed for a given request."""

    def __init__(self, db: Database, projects_dir: str = "./projects"):
        self.db = db
        self.projects_dir = Path(projects_dir).resolve()
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def resolve(
        self,
        user_message: str,
        active_project_id: Optional[int] = None,
    ) -> tuple[str, Optional[int]]:
        """
        Determine the target directory for a request.

        Returns:
            (directory_path, project_id) - project_id may be None for scratch
        """
        # 1. Check if user mentions an existing project by name
        project = self._match_existing_project(user_message)
        if project:
            return project.directory, project.id

        # 2. Use active project if we have one
        if active_project_id:
            project = self.db.get_project(active_project_id)
            if project and os.path.exists(project.directory):
                return project.directory, project.id

        # 3. Detect if this is a "build new project" request
        project_name = self._extract_project_name(user_message)
        if project_name:
            return self._create_project_dir(project_name), None

        # 4. Default to a scratch directory
        scratch_dir = str(self.projects_dir / "_scratch")
        os.makedirs(scratch_dir, exist_ok=True)
        return scratch_dir, None

    def create_project_for_dir(
        self,
        directory: str,
        name: str,
        description: str = "",
        plan: Optional[dict] = None,
    ) -> Project:
        """Create a database record for a project directory."""
        project = self.db.create_project(
            name=name,
            directory=directory,
            description=description,
            plan=plan,
        )
        return project

    def _match_existing_project(self, message: str) -> Optional[Project]:
        """Check if the message references an existing project by name."""
        projects = self.db.list_projects(limit=20)
        if not projects:
            return None

        msg_lower = message.lower()
        for project in projects:
            # Check if project name appears in the message
            if project.name.lower() in msg_lower:
                return project

        return None

    def _extract_project_name(self, message: str) -> Optional[str]:
        """Try to extract a project name from a build request."""
        build_patterns = [
            r'build\s+(?:me\s+)?(?:a\s+)?(.+?)(?:\s+app|\s+tool|\s+website|\s+project)?$',
            r'create\s+(?:a\s+)?(.+?)(?:\s+app|\s+tool|\s+website|\s+project)?$',
            r'make\s+(?:me\s+)?(?:a\s+)?(.+?)(?:\s+app|\s+tool|\s+website|\s+project)?$',
        ]

        for pattern in build_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                raw = match.group(1).strip()
                return self._sanitize_name(raw)

        return None

    def _sanitize_name(self, name: str) -> str:
        """Convert a natural language name into a safe directory name."""
        # Remove special characters, keep alphanumeric and spaces
        clean = re.sub(r'[^\w\s-]', '', name)
        # Replace spaces with hyphens
        clean = re.sub(r'\s+', '-', clean.strip())
        # Lowercase
        clean = clean.lower()
        # Truncate
        clean = clean[:50]
        return clean or "project"

    def _create_project_dir(self, name: str) -> str:
        """Create a new project directory, handling name conflicts."""
        base = str(self.projects_dir / name)
        target = base

        counter = 1
        while os.path.exists(target):
            target = f"{base}-{counter}"
            counter += 1

        os.makedirs(target, exist_ok=True)
        return target
