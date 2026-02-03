"""
Orchestrator - coordinates multi-agent collaboration.

This is the core engine that:
1. Receives user requests
2. Routes tasks to appropriate agents
3. Manages the build workflow
4. Handles verification and iteration
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum

from ..agents import PlannerAgent, CoderAgent, ReviewerAgent


class ProjectStatus(Enum):
    PLANNING = "planning"
    CODING = "coding"
    REVIEWING = "reviewing"
    TESTING = "testing"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class ProjectState:
    """Tracks the current state of a project being built."""
    name: str
    user_request: str
    status: ProjectStatus = ProjectStatus.PLANNING
    plan: Optional[dict] = None
    files: dict = field(default_factory=dict)  # path -> content
    current_task: int = 0
    errors: list = field(default_factory=list)
    messages: list = field(default_factory=list)  # For UI


class Orchestrator:
    """
    Main orchestration engine for the multi-agent system.

    Usage:
        orchestrator = Orchestrator(on_event=my_callback)
        result = await orchestrator.build("Create a todo app")
    """

    def __init__(
        self,
        projects_dir: str = "./projects",
        on_event: Optional[Callable[[str, str, Any], None]] = None
    ):
        self.projects_dir = Path(projects_dir)
        self.projects_dir.mkdir(exist_ok=True)
        self.on_event = on_event  # Callback for UI updates
        self.state: Optional[ProjectState] = None

        # Initialize agents with message callback
        agent_callback = self._create_agent_callback()
        self.planner = PlannerAgent(on_message=agent_callback)
        self.coder = CoderAgent(on_message=agent_callback)
        self.reviewer = ReviewerAgent(on_message=agent_callback)

    def _create_agent_callback(self) -> Callable:
        """Create a callback that routes agent messages to the UI."""
        def callback(agent_name: str, msg_type: str, content: str):
            self.emit("agent_message", {
                "agent": agent_name,
                "type": msg_type,
                "content": content
            })
        return callback

    def emit(self, event_type: str, data: Any):
        """Emit an event to the UI."""
        if self.state:
            self.state.messages.append({"type": event_type, "data": data})
        if self.on_event:
            self.on_event(event_type, data)

    def build(self, user_request: str) -> dict:
        """
        Main entry point - build software from a user request.

        Args:
            user_request: Natural language description of what to build

        Returns:
            dict with project info and generated files
        """
        self.emit("status", "Starting build process...")

        # Initialize project state
        self.state = ProjectState(
            name="new-project",
            user_request=user_request
        )

        try:
            # Phase 1: Planning
            self._phase_planning()

            # Phase 2: Coding
            self._phase_coding()

            # Phase 3: Review
            self._phase_review()

            # Phase 4: Save files
            self._save_project()

            self.state.status = ProjectStatus.COMPLETE
            self.emit("complete", {
                "project_name": self.state.name,
                "files": list(self.state.files.keys())
            })

            return {
                "success": True,
                "project_name": self.state.name,
                "files": self.state.files,
                "plan": self.state.plan
            }

        except Exception as e:
            self.state.status = ProjectStatus.FAILED
            self.state.errors.append(str(e))
            self.emit("error", str(e))
            return {
                "success": False,
                "error": str(e),
                "partial_files": self.state.files
            }

    def _phase_planning(self):
        """Phase 1: Create implementation plan."""
        self.state.status = ProjectStatus.PLANNING
        self.emit("phase", "Planning")

        response = self.planner.think(
            f"Create an implementation plan for: {self.state.user_request}"
        )

        # Parse the JSON plan from response
        plan = self._extract_json(response)
        if not plan:
            raise ValueError("Planner failed to produce a valid plan")

        self.state.plan = plan
        self.state.name = plan.get("project_name", "project")
        self.emit("plan_ready", plan)

    def _phase_coding(self):
        """Phase 2: Implement each task."""
        self.state.status = ProjectStatus.CODING
        self.emit("phase", "Coding")

        tasks = self.state.plan.get("tasks", [])

        for i, task in enumerate(tasks):
            self.state.current_task = i + 1
            self.emit("task_start", {
                "task_number": i + 1,
                "total": len(tasks),
                "title": task.get("title", "Task")
            })

            # Build context with existing files
            context = {
                "task": task,
                "existing_files": self.state.files,
                "tech_stack": self.state.plan.get("tech_stack", {})
            }

            response = self.coder.think(
                f"Implement this task:\n{json.dumps(task, indent=2)}",
                context=json.dumps(context, indent=2)
            )

            # Parse the code output
            code_output = self._extract_json(response)
            if code_output and "code" in code_output:
                file_path = code_output.get("file_path", f"file_{i}.py")
                self.state.files[file_path] = code_output["code"]
                self.emit("file_created", {
                    "path": file_path,
                    "explanation": code_output.get("explanation", "")
                })

    def _phase_review(self):
        """Phase 3: Review the code."""
        self.state.status = ProjectStatus.REVIEWING
        self.emit("phase", "Reviewing")

        # Review all files
        all_code = "\n\n".join([
            f"# File: {path}\n{content}"
            for path, content in self.state.files.items()
        ])

        response = self.reviewer.think(
            "Review this code for bugs, security issues, and correctness:",
            context=all_code
        )

        review = self._extract_json(response)
        if review:
            self.emit("review_complete", review)

            # If there are critical issues, try to fix them
            critical_issues = [
                issue for issue in review.get("issues", [])
                if issue.get("severity") == "critical"
            ]

            if critical_issues:
                self.emit("fixing_issues", critical_issues)
                self._fix_issues(critical_issues)

    def _fix_issues(self, issues: list):
        """Attempt to fix critical issues found in review."""
        for issue in issues:
            self.emit("fixing", issue)

            response = self.coder.think(
                f"Fix this critical issue:\n{json.dumps(issue, indent=2)}",
                context=json.dumps({
                    "files": self.state.files,
                    "issue": issue
                }, indent=2)
            )

            code_output = self._extract_json(response)
            if code_output and "code" in code_output:
                file_path = code_output.get("file_path")
                if file_path:
                    self.state.files[file_path] = code_output["code"]
                    self.emit("file_updated", {"path": file_path})

    def _save_project(self):
        """Save all generated files to disk."""
        project_dir = self.projects_dir / self.state.name
        project_dir.mkdir(exist_ok=True)

        for file_path, content in self.state.files.items():
            full_path = project_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            self.emit("file_saved", str(full_path))

        # Save the plan as well
        plan_path = project_dir / "plan.json"
        plan_path.write_text(json.dumps(self.state.plan, indent=2))

    def _extract_json(self, text: str) -> Optional[dict]:
        """Extract JSON from a response that might have markdown."""
        # Try to find JSON in code blocks
        import re

        # Look for ```json ... ``` blocks
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try parsing the whole thing as JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find any {...} block
        brace_match = re.search(r'\{.*\}', text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None
