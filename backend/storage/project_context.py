"""
Project Context Injection - gives agents awareness of the project they're working on.

Before any agent runs, this module builds a context string containing:
- Project file tree
- Key config files (package.json, requirements.txt, etc.)
- Previous decisions stored in memory
- Recent conversation summary

This gets injected into the agent's prompt so they know what exists.
"""

import os
from pathlib import Path
from typing import Optional

from .database import Database


# Files that are worth reading for context (small config/metadata files)
KEY_FILES = [
    "package.json", "requirements.txt", "pyproject.toml", "Cargo.toml",
    "Makefile", "Dockerfile", "docker-compose.yml",
    "tsconfig.json", ".eslintrc.json", "setup.py", "setup.cfg",
    "README.md", "README.txt",
]

# Max size of a key file to include inline (2KB)
MAX_KEY_FILE_SIZE = 2048

# Max files to list in tree
MAX_TREE_FILES = 100

# Directories to skip
SKIP_DIRS = {
    '.git', 'node_modules', '__pycache__', '.venv', 'venv',
    '.next', 'dist', 'build', '.cache', '.tox', 'egg-info',
}


class ProjectContext:
    """Builds context strings about a project for agent prompts."""

    def __init__(self, db: Database):
        self.db = db

    def build_context(self, project_id: int) -> str:
        """
        Build a full context string for a project.

        Returns a formatted string suitable for injection into agent prompts.
        """
        project = self.db.get_project(project_id)
        if not project:
            return ""

        parts = []

        # Project info
        parts.append(f"## Active Project: {project.name}")
        if project.description:
            parts.append(f"Description: {project.description}")
        parts.append(f"Directory: {project.directory}")
        parts.append("")

        # File tree
        tree = self._build_file_tree(project.directory)
        if tree:
            parts.append("## Project Files")
            parts.append("```")
            parts.append(tree)
            parts.append("```")
            parts.append("")

        # Key config files
        configs = self._read_key_files(project.directory)
        if configs:
            parts.append("## Key Configuration")
            for filename, content in configs.items():
                parts.append(f"### {filename}")
                parts.append(f"```")
                parts.append(content)
                parts.append("```")
                parts.append("")

        # Stored decisions/memory
        memory = self.db.get_all_memory(project_id)
        if memory:
            parts.append("## Project Decisions")
            for key, value in memory.items():
                parts.append(f"- **{key}**: {value}")
            parts.append("")

        return "\n".join(parts)

    def build_summary(self, project_id: int) -> str:
        """Build a short summary (for router context, not full agent prompts)."""
        project = self.db.get_project(project_id)
        if not project:
            return ""

        parts = [f"Project: {project.name}"]
        if project.description:
            parts.append(f"Description: {project.description}")

        files = self._list_files(project.directory)
        if files:
            parts.append(f"Files ({len(files)}): {', '.join(files[:10])}")
            if len(files) > 10:
                parts.append(f"  ...and {len(files) - 10} more")

        return "\n".join(parts)

    def _build_file_tree(self, directory: str) -> str:
        """Build an indented file tree string."""
        if not os.path.exists(directory):
            return ""

        lines = []
        file_count = 0

        for root, dirs, files in os.walk(directory):
            # Filter out ignored dirs
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith('.'))

            level = root.replace(directory, '').count(os.sep)
            indent = '  ' * level
            dirname = os.path.basename(root)

            if level == 0:
                lines.append(f"{dirname}/")
            else:
                lines.append(f"{indent}{dirname}/")

            sub_indent = '  ' * (level + 1)
            for f in sorted(files):
                if f.startswith('.') and f not in ('.env.example', '.gitignore'):
                    continue
                lines.append(f"{sub_indent}{f}")
                file_count += 1

                if file_count >= MAX_TREE_FILES:
                    lines.append(f"{sub_indent}... (truncated)")
                    return '\n'.join(lines)

        return '\n'.join(lines)

    def _list_files(self, directory: str) -> list[str]:
        """List relative file paths."""
        if not os.path.exists(directory):
            return []

        files = []
        for root, dirs, filenames in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
            for f in filenames:
                if not f.startswith('.'):
                    rel = os.path.relpath(os.path.join(root, f), directory)
                    files.append(rel)
                    if len(files) >= MAX_TREE_FILES:
                        return files
        return files

    def _read_key_files(self, directory: str) -> dict[str, str]:
        """Read small config files that provide useful context."""
        configs = {}

        for filename in KEY_FILES:
            filepath = os.path.join(directory, filename)
            if os.path.exists(filepath):
                try:
                    size = os.path.getsize(filepath)
                    if size <= MAX_KEY_FILE_SIZE:
                        with open(filepath, 'r', errors='replace') as f:
                            configs[filename] = f.read()
                except OSError:
                    pass

        return configs
