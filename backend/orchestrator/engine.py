"""
Orchestrator Engine - coordinates multi-agent pipeline builds.

Pipeline: Plan → Code → Verify → Review → Test → Debug loop

Key paradigm shift from v1:
- Agents use real tools to create/modify files on disk
- No more _extract_json() to parse code strings
- Verification happens via agent tools (Bash) not sandbox
- The sandbox is still available for isolated execution if needed
"""

import json
import os
from pathlib import Path
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum

from ..agents import (
    PlannerAgent,
    CoderAgent,
    ReviewerAgent,
    TesterAgent,
    DebuggerAgent
)
from .dialogue import run_code_review_dialogue, run_test_debug_dialogue


class ProjectStatus(Enum):
    PLANNING = "planning"
    CODING = "coding"
    REVIEWING = "reviewing"
    TESTING = "testing"
    DEBUGGING = "debugging"
    VERIFYING = "verifying"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class ProjectState:
    """Tracks the current state of a project being built."""
    name: str
    user_request: str
    status: ProjectStatus = ProjectStatus.PLANNING
    plan: Optional[dict] = None
    project_dir: Optional[str] = None
    errors: list = field(default_factory=list)
    messages: list = field(default_factory=list)
    iterations: int = 0
    max_iterations: int = 3


class Orchestrator:
    """
    Pipeline orchestration engine for full project builds.

    Pipeline:
    1. Planning - Break down into tasks (Planner agent)
    2. Coding - Implement tasks (Coder agent creates files directly)
    3. Review - Check for issues (Reviewer agent reads files directly)
    4. Testing - Write and run tests (Tester agent)
    5. Debug loop - Fix problems (Debugger agent)
    """

    def __init__(
        self,
        projects_dir: str = "./projects",
        on_event: Optional[Callable[[str, Any], None]] = None
    ):
        self.projects_dir = Path(projects_dir).resolve()
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.on_event = on_event
        self.state: Optional[ProjectState] = None

        # Initialize agents with message callback
        agent_callback = self._create_agent_callback()
        self.planner = PlannerAgent(on_message=agent_callback)
        self.coder = CoderAgent(on_message=agent_callback)
        self.reviewer = ReviewerAgent(on_message=agent_callback)
        self.tester = TesterAgent(on_message=agent_callback)
        self.debugger = DebuggerAgent(on_message=agent_callback)

        # Agents that need project directory access
        self._tool_agents = [
            self.coder, self.reviewer, self.tester, self.debugger
        ]

    def _create_agent_callback(self) -> Callable:
        """Create a callback that routes agent messages to the UI."""
        def callback(agent_name: str, msg_type: str, content: Any):
            self.emit("agent_message", {
                "agent": agent_name,
                "type": msg_type,
                "content": content if isinstance(content, str) else json.dumps(content)
            })
        return callback

    def emit(self, event_type: str, data: Any):
        """Emit an event to the UI."""
        if self.state:
            self.state.messages.append({"type": event_type, "data": data})
        if self.on_event:
            self.on_event(event_type, data)

    def _setup_project_dir(self, project_name: str) -> str:
        """Create project directory and configure agents."""
        project_dir = str(self.projects_dir / project_name)
        os.makedirs(project_dir, exist_ok=True)

        for agent in self._tool_agents:
            agent.set_project_dir(project_dir)

        return project_dir

    def _list_project_files(self, project_dir: str) -> list[str]:
        """List files in the project directory."""
        files = []
        try:
            for root, dirs, filenames in os.walk(project_dir):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules' and d != '__pycache__']
                for f in filenames:
                    if not f.startswith('.'):
                        rel = os.path.relpath(os.path.join(root, f), project_dir)
                        files.append(rel)
        except OSError:
            pass
        return files[:100]

    def build(self, user_request: str) -> dict:
        """
        Main entry point - build software from a user request.

        Pipeline:
        1. Planning - Break down into tasks
        2. Coding - Implement (agents create files directly)
        3. Review - Check for issues
        4. Testing - Write and run tests
        5. Debug loop - Fix any problems
        """
        self.emit("status", "Starting build process...")

        self.state = ProjectState(
            name="new-project",
            user_request=user_request
        )

        try:
            # Phase 1: Planning
            self._phase_planning()

            # Phase 2: Coding (agents create files directly)
            self._phase_coding()

            # Phase 3: Review
            self._phase_review()

            # Phase 4: Testing (includes running tests)
            self._phase_testing()

            self.state.status = ProjectStatus.COMPLETE
            files = self._list_project_files(self.state.project_dir)

            self.emit("complete", {
                "project_name": self.state.name,
                "files": files
            })

            return {
                "success": True,
                "project_name": self.state.name,
                "project_dir": self.state.project_dir,
                "files": files,
                "plan": self.state.plan
            }

        except Exception as e:
            self.state.status = ProjectStatus.FAILED
            self.state.errors.append(str(e))
            self.emit("error", str(e))
            return {
                "success": False,
                "error": str(e),
                "partial_files": self._list_project_files(self.state.project_dir) if self.state.project_dir else []
            }

    def _phase_planning(self):
        """Phase 1: Create implementation plan."""
        self.state.status = ProjectStatus.PLANNING
        self.emit("phase", "Planning")

        plan = self.planner.think_json(
            f"Create an implementation plan for: {self.state.user_request}"
        )

        if plan.get("error"):
            raise ValueError("Planner failed to produce a valid plan")

        self.state.plan = plan
        self.state.name = plan.get("project_name", "project")
        self.state.project_dir = self._setup_project_dir(self.state.name)
        self.emit("plan_ready", plan)

    def _phase_coding(self):
        """Phase 2: Implement the plan. Coder creates files directly via tools."""
        self.state.status = ProjectStatus.CODING
        self.emit("phase", "Coding")

        tasks = self.state.plan.get("tasks", [])
        task_descriptions = "\n".join([
            f"{i+1}. {t.get('title', 'Task')}: {t.get('description', '')}"
            for i, t in enumerate(tasks)
        ])

        coding_prompt = f"""Implement this project in the current directory.

Project: {self.state.plan.get('summary', self.state.user_request)}
Tech stack: {json.dumps(self.state.plan.get('tech_stack', {}), indent=2)}

Tasks to implement:
{task_descriptions}

Files to create:
{json.dumps(self.state.plan.get('files_to_create', []), indent=2)}

Create ALL the files needed. Use the Write tool for each file.
After creating files, use Bash to verify the code runs (syntax check at minimum)."""

        self.coder.think(coding_prompt)

        # Report created files
        files = self._list_project_files(self.state.project_dir)
        for f in files:
            self.emit("file_created", {"path": f})

    def _phase_review(self):
        """Phase 3: Review the code with Coder↔Reviewer dialogue."""
        self.state.status = ProjectStatus.REVIEWING
        self.emit("phase", "Reviewing")

        review_response = run_code_review_dialogue(
            coder=self.coder,
            reviewer=self.reviewer,
            task=(
                "Review all files in the current project directory. "
                "Check for bugs, security issues, and correctness. "
                "Use Glob to find files, Read to examine them, Grep to search for patterns."
            ),
            emit=self.on_event,
            max_rounds=2
        )

        self.emit("review_complete", {"summary": review_response[:500]})

    def _phase_testing(self):
        """Phase 4: Write and run tests with Tester↔Debugger dialogue."""
        self.state.status = ProjectStatus.TESTING
        self.emit("phase", "Testing")

        test_response = run_test_debug_dialogue(
            tester=self.tester,
            debugger=self.debugger,
            task=(
                "Write and run tests for the project in the current directory. "
                "Use Glob/Read to understand the code, Write to create test files, "
                "Bash to run them. Report what passes and what fails."
            ),
            emit=self.on_event,
            max_rounds=2
        )

        self.emit("test_complete", {"summary": test_response[:500]})
