"""
Orchestrator - coordinates multi-agent collaboration.

This is the core engine that:
1. Receives user requests
2. Routes tasks to appropriate agents
3. Manages the build workflow
4. Executes and verifies generated code
5. Iterates until code works
"""

import json
import os
import re
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
from ..sandbox import Sandbox


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
    files: dict = field(default_factory=dict)  # path -> content
    test_files: dict = field(default_factory=dict)  # test path -> content
    current_task: int = 0
    errors: list = field(default_factory=list)
    messages: list = field(default_factory=list)  # For UI
    execution_results: list = field(default_factory=list)
    iterations: int = 0
    max_iterations: int = 3  # Max debug attempts


class Orchestrator:
    """
    Main orchestration engine for the multi-agent system.

    Features:
    - Multi-agent coordination (Planner → Coder → Reviewer → Tester)
    - Code execution sandbox
    - Automatic debugging loop
    - Verification before completion
    """

    def __init__(
        self,
        projects_dir: str = "./projects",
        on_event: Optional[Callable[[str, str, Any], None]] = None
    ):
        self.projects_dir = Path(projects_dir)
        self.projects_dir.mkdir(exist_ok=True)
        self.on_event = on_event
        self.state: Optional[ProjectState] = None
        self.sandbox: Optional[Sandbox] = None

        # Initialize agents with message callback
        agent_callback = self._create_agent_callback()
        self.planner = PlannerAgent(on_message=agent_callback)
        self.coder = CoderAgent(on_message=agent_callback)
        self.reviewer = ReviewerAgent(on_message=agent_callback)
        self.tester = TesterAgent(on_message=agent_callback)
        self.debugger = DebuggerAgent(on_message=agent_callback)

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

        Pipeline:
        1. Planning - Break down into tasks
        2. Coding - Implement each task
        3. Verification - Run and test code
        4. Review - Check for issues
        5. Debug loop - Fix any problems
        6. Save - Write to disk
        """
        self.emit("status", "Starting build process...")

        # Initialize project state
        self.state = ProjectState(
            name="new-project",
            user_request=user_request
        )

        # Create sandbox for code execution
        self.sandbox = Sandbox(timeout=30)

        try:
            # Phase 1: Planning
            self._phase_planning()

            # Phase 2: Coding
            self._phase_coding()

            # Phase 3: Verification (run the code)
            self._phase_verification()

            # Phase 4: Review
            self._phase_review()

            # Phase 5: Testing
            self._phase_testing()

            # Phase 6: Save files
            self._save_project()

            self.state.status = ProjectStatus.COMPLETE
            self.emit("complete", {
                "project_name": self.state.name,
                "files": list(self.state.files.keys()),
                "test_files": list(self.state.test_files.keys())
            })

            return {
                "success": True,
                "project_name": self.state.name,
                "files": self.state.files,
                "test_files": self.state.test_files,
                "plan": self.state.plan,
                "execution_results": self.state.execution_results
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

        finally:
            # Cleanup sandbox
            if self.sandbox:
                self.sandbox.cleanup()

    def _phase_planning(self):
        """Phase 1: Create implementation plan."""
        self.state.status = ProjectStatus.PLANNING
        self.emit("phase", "Planning")

        response = self.planner.think(
            f"Create an implementation plan for: {self.state.user_request}"
        )

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

            context = {
                "task": task,
                "existing_files": self.state.files,
                "tech_stack": self.state.plan.get("tech_stack", {})
            }

            response = self.coder.think(
                f"Implement this task:\n{json.dumps(task, indent=2)}",
                context=json.dumps(context, indent=2)
            )

            code_output = self._extract_json(response)
            if code_output and "code" in code_output:
                file_path = code_output.get("file_path", f"file_{i}.py")
                self.state.files[file_path] = code_output["code"]
                self.emit("file_created", {
                    "path": file_path,
                    "explanation": code_output.get("explanation", "")
                })

    def _phase_verification(self):
        """Phase 3: Run and verify the code."""
        self.state.status = ProjectStatus.VERIFYING
        self.emit("phase", "Verifying")

        if not self.state.files:
            self.emit("warning", "No files to verify")
            return

        # Setup sandbox with generated files
        self.sandbox.setup(self.state.name)
        self.sandbox.write_files(self.state.files)

        # Determine how to run based on tech stack
        tech_stack = self.state.plan.get("tech_stack", {})
        language = tech_stack.get("language", "python").lower()

        # Find main entry point
        main_file = self._find_main_file(language)

        if not main_file:
            self.emit("warning", "Could not find main entry point")
            return

        self.emit("executing", {"file": main_file, "language": language})

        # Lint first
        if language == "python":
            lint_result = self.sandbox.lint_python(main_file)
            if not lint_result.success:
                self.emit("lint_error", {
                    "file": main_file,
                    "error": lint_result.stderr
                })
                # Try to fix syntax errors
                self._debug_loop(f"Syntax error in {main_file}: {lint_result.stderr}")

        # Install dependencies if specified
        deps = tech_stack.get("dependencies", [])
        if deps and language == "python":
            self.emit("installing_deps", deps)
            self.sandbox.install_python_deps(deps)

        # Run the code
        if language == "python":
            result = self.sandbox.run_python(main_file)
        elif language in ["javascript", "js", "node"]:
            result = self.sandbox.run_node(main_file)
        else:
            result = self.sandbox.run_command(f"python3 {main_file}")

        self.state.execution_results.append({
            "file": main_file,
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr
        })

        self.emit("execution_result", {
            "success": result.success,
            "stdout": result.stdout[:1000],
            "stderr": result.stderr[:1000]
        })

        # If execution failed, enter debug loop
        if not result.success and result.stderr:
            self._debug_loop(result.stderr)

    def _debug_loop(self, error: str):
        """Attempt to fix errors through the debugger agent."""
        self.state.status = ProjectStatus.DEBUGGING

        while self.state.iterations < self.state.max_iterations:
            self.state.iterations += 1
            self.emit("debug_attempt", {
                "attempt": self.state.iterations,
                "max": self.state.max_iterations,
                "error": error[:500]
            })

            # Ask debugger to analyze and fix
            response = self.debugger.think(
                f"Fix this error:\n{error}",
                context=json.dumps({
                    "files": self.state.files,
                    "tech_stack": self.state.plan.get("tech_stack", {})
                }, indent=2)
            )

            fix = self._extract_json(response)
            if not fix:
                self.emit("debug_failed", "Could not parse fix")
                break

            if fix.get("need_more_info"):
                self.emit("debug_question", fix.get("question", "Need more context"))
                break

            # Apply the fix
            file_path = fix.get("file_path")
            if file_path and "fix" in fix:
                new_code = fix["fix"].get("new_code")
                if new_code:
                    # If it's a full file replacement
                    if len(new_code) > 100:
                        self.state.files[file_path] = new_code
                    else:
                        # Partial fix - try to apply
                        old_code = fix["fix"].get("old_code", "")
                        if old_code and file_path in self.state.files:
                            self.state.files[file_path] = self.state.files[file_path].replace(
                                old_code, new_code
                            )

                    self.emit("fix_applied", {
                        "file": file_path,
                        "diagnosis": fix.get("diagnosis", "")
                    })

                    # Update sandbox and retry
                    self.sandbox.write_file(file_path, self.state.files[file_path])

                    # Re-run
                    result = self.sandbox.run_python(file_path)
                    if result.success:
                        self.emit("debug_success", "Code runs successfully!")
                        return
                    else:
                        error = result.stderr

            else:
                self.emit("debug_failed", "No actionable fix provided")
                break

        self.emit("debug_exhausted", f"Could not fix after {self.state.iterations} attempts")

    def _phase_review(self):
        """Phase 4: Review the code."""
        self.state.status = ProjectStatus.REVIEWING
        self.emit("phase", "Reviewing")

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

            critical_issues = [
                issue for issue in review.get("issues", [])
                if issue.get("severity") == "critical"
            ]

            if critical_issues:
                self.emit("fixing_issues", critical_issues)
                self._fix_issues(critical_issues)

    def _phase_testing(self):
        """Phase 5: Generate and run tests."""
        self.state.status = ProjectStatus.TESTING
        self.emit("phase", "Testing")

        # Ask tester to write tests
        response = self.tester.think(
            "Write tests for this code:",
            context=json.dumps({
                "files": self.state.files,
                "plan": self.state.plan
            }, indent=2)
        )

        test_output = self._extract_json(response)
        if test_output and "code" in test_output:
            test_path = test_output.get("file_path", "test_main.py")
            self.state.test_files[test_path] = test_output["code"]

            self.emit("test_created", {
                "path": test_path,
                "description": test_output.get("description", "")
            })

            # Write test to sandbox and run
            self.sandbox.write_file(test_path, test_output["code"])

            run_cmd = test_output.get("run_command", f"python3 -m pytest {test_path} -v")
            result = self.sandbox.run_command(run_cmd)

            self.emit("test_result", {
                "success": result.success,
                "output": result.stdout[:2000] if result.success else result.stderr[:2000]
            })

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

    def _find_main_file(self, language: str) -> Optional[str]:
        """Find the main entry point file."""
        common_names = {
            "python": ["main.py", "app.py", "run.py", "__main__.py"],
            "javascript": ["index.js", "main.js", "app.js"],
            "js": ["index.js", "main.js", "app.js"],
            "node": ["index.js", "main.js", "app.js"]
        }

        for name in common_names.get(language, ["main.py"]):
            if name in self.state.files:
                return name

        # Return first file if no common name found
        if self.state.files:
            return list(self.state.files.keys())[0]

        return None

    def _save_project(self):
        """Save all generated files to disk."""
        project_dir = self.projects_dir / self.state.name
        project_dir.mkdir(exist_ok=True)

        # Save code files
        for file_path, content in self.state.files.items():
            full_path = project_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            self.emit("file_saved", str(full_path))

        # Save test files
        tests_dir = project_dir / "tests"
        tests_dir.mkdir(exist_ok=True)
        for file_path, content in self.state.test_files.items():
            full_path = tests_dir / file_path
            full_path.write_text(content)

        # Save the plan
        plan_path = project_dir / "plan.json"
        plan_path.write_text(json.dumps(self.state.plan, indent=2))

        # Save execution log
        log_path = project_dir / "build_log.json"
        log_path.write_text(json.dumps({
            "user_request": self.state.user_request,
            "iterations": self.state.iterations,
            "execution_results": self.state.execution_results,
            "errors": self.state.errors
        }, indent=2))

    def _extract_json(self, text: str) -> Optional[dict]:
        """Extract JSON from a response that might have markdown."""
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
