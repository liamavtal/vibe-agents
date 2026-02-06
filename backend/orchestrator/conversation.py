"""
Conversational Orchestrator - Smart agent routing with project persistence.

This is what makes Vibe Agents work like Claude Code:
1. You chat naturally
2. The Router analyzes your message
3. It decides which agents (if any) to use
4. Agents work directly on files (no JSON code string parsing)
5. You get real-time streaming updates
6. Projects persist across sessions (close browser, come back)

Persistence features:
- Projects saved to SQLite database
- Agent CLI sessions preserved per project+agent
- Project context injected before agent work
- Smart file placement based on request context
"""

import json
import os
from pathlib import Path
from typing import Optional, Callable, Any
from dataclasses import dataclass, field

from ..agents import (
    RouterAgent,
    PlannerAgent,
    CoderAgent,
    ReviewerAgent,
    TesterAgent,
    DebuggerAgent
)
from ..storage import Database, ProjectContext, FileLocator
from ..integrations import GitHubIntegration
from .dialogue import run_code_review_dialogue, run_test_debug_dialogue


@dataclass
class ConversationState:
    """Tracks the ongoing conversation and any active project."""
    messages: list = field(default_factory=list)
    active_project_id: Optional[int] = None
    active_project_name: Optional[str] = None
    project_dir: Optional[str] = None
    project_plan: Optional[dict] = None


class ConversationalOrchestrator:
    """
    The conversational interface to the multi-agent system.

    Now with persistence:
    - Projects saved to SQLite (~/.vibe-agents/vibe-agents.db)
    - Agent sessions preserved per project+agent via --session-id
    - Project context injected into agent prompts
    - Smart file placement based on user intent
    """

    def __init__(
        self,
        projects_dir: str = "./projects",
        on_event: Optional[Callable[[str, Any], None]] = None,
        db: Optional[Database] = None,
    ):
        self.projects_dir = Path(projects_dir).resolve()
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.on_event = on_event
        self.state = ConversationState()

        # Persistence layer
        self.db = db or Database()
        self.project_context = ProjectContext(self.db)
        self.file_locator = FileLocator(self.db, str(self.projects_dir))

        # GitHub integration
        self.github = GitHubIntegration(
            projects_dir=str(self.projects_dir),
            on_event=on_event
        )

        # Initialize agents with message callback
        agent_callback = self._create_agent_callback()
        self.router = RouterAgent(on_message=agent_callback)
        self.planner = PlannerAgent(on_message=agent_callback)
        self.coder = CoderAgent(on_message=agent_callback)
        self.reviewer = ReviewerAgent(on_message=agent_callback)
        self.tester = TesterAgent(on_message=agent_callback)
        self.debugger = DebuggerAgent(on_message=agent_callback)

        # All agents that work on files
        self._tool_agents = [
            self.coder, self.reviewer, self.tester, self.debugger
        ]

        # Named agent map for session persistence
        self._agents_by_name = {
            "Router": self.router,
            "Planner": self.planner,
            "Coder": self.coder,
            "Reviewer": self.reviewer,
            "Tester": self.tester,
            "Debugger": self.debugger,
        }

    def _create_agent_callback(self) -> Callable:
        """Route agent messages to the UI and capture session IDs."""
        def callback(agent_name: str, msg_type: str, content: Any):
            self.emit("agent_message", {
                "agent": agent_name,
                "type": msg_type,
                "content": content if isinstance(content, str) else json.dumps(content)
            })
        return callback

    def emit(self, event_type: str, data: Any):
        """Emit an event to the UI."""
        if self.on_event:
            self.on_event(event_type, data)

    # ==================== Session Persistence ====================

    def _restore_sessions(self, project_id: int):
        """Restore agent CLI session IDs from database."""
        sessions = self.db.get_all_sessions(project_id)
        for agent_name, session_id in sessions.items():
            agent = self._agents_by_name.get(agent_name)
            if agent:
                agent.set_session_id(session_id)

    def _save_sessions(self, project_id: int):
        """Save current agent CLI session IDs to database."""
        for agent_name, agent in self._agents_by_name.items():
            sid = agent._session_id
            if sid:
                self.db.save_session(project_id, agent_name, sid)

    # ==================== Project Setup ====================

    def _setup_project(self, project_name: str, description: str = "",
                       plan: Optional[dict] = None) -> tuple[str, int]:
        """
        Set up a project directory and database record.

        Returns (project_dir, project_id).
        """
        if self.state.active_project_id and self.state.project_dir:
            # Already have an active project
            return self.state.project_dir, self.state.active_project_id

        # Use file locator for smart placement
        project_dir, existing_id = self.file_locator.resolve(
            project_name,
            active_project_id=self.state.active_project_id,
        )

        if existing_id:
            # Resuming existing project
            project_id = existing_id
            project = self.db.get_project(project_id)
            if project:
                self.state.active_project_name = project.name
                self._restore_sessions(project_id)
        else:
            # Create new project record
            project = self.file_locator.create_project_for_dir(
                directory=project_dir,
                name=project_name,
                description=description,
                plan=plan,
            )
            project_id = project.id

        self.state.active_project_id = project_id
        self.state.active_project_name = project_name
        self.state.project_dir = project_dir

        # Point all tool-using agents at this directory
        for agent in self._tool_agents:
            agent.set_project_dir(project_dir)

        self.emit("project_active", {
            "id": project_id,
            "name": project_name,
            "directory": project_dir,
        })

        return project_dir, project_id

    def _ensure_project_dir(self, project_name: str = "project") -> str:
        """Ensure a project directory exists and return its path."""
        project_dir, _ = self._setup_project(project_name)
        return project_dir

    # ==================== Resume Project ====================

    def resume_project(self, project_id: int) -> dict:
        """Resume a previously saved project."""
        project = self.db.get_project(project_id)
        if not project:
            return {"error": "Project not found"}

        self.state.active_project_id = project.id
        self.state.active_project_name = project.name
        self.state.project_dir = project.directory

        if project.plan_json:
            try:
                self.state.project_plan = json.loads(project.plan_json)
            except json.JSONDecodeError:
                pass

        # Restore agent sessions
        self._restore_sessions(project.id)

        # Point agents at project directory
        for agent in self._tool_agents:
            agent.set_project_dir(project.directory)

        # Build context summary
        context_summary = self.project_context.build_summary(project.id)

        self.emit("project_resumed", {
            "id": project.id,
            "name": project.name,
            "directory": project.directory,
            "context": context_summary,
        })

        return {
            "success": True,
            "project": project.to_dict(),
            "context": context_summary,
        }

    # ==================== Main Chat ====================

    def chat(self, user_message: str) -> dict:
        """
        Main entry point - process a user message.

        Returns a response dict with the action taken and result.
        """
        # Add to conversation history
        self.state.messages.append({
            "role": "user",
            "content": user_message
        })

        # Build context for the router
        context = self._build_context()

        # Get routing decision
        self.emit("routing", {"message": "Analyzing your request..."})
        decision = self.router.route(user_message, context)

        self.emit("route_decision", {
            "action": decision.get("action", "UNKNOWN"),
            "reasoning": decision.get("reasoning", ""),
            "confidence": decision.get("confidence", 0)
        })

        # Execute based on decision
        action = decision.get("action", "CONVERSATION")

        if action == "CONVERSATION":
            response = decision.get("response", "I'm not sure how to help with that.")
            result = {"type": "conversation", "response": response}

        elif action == "BUILD":
            result = self._execute_build(decision.get("task_for_agents", user_message))

        elif action == "CODE_ONLY":
            result = self._execute_code_only(decision.get("task_for_agents", user_message))

        elif action == "FIX":
            result = self._execute_fix(decision.get("task_for_agents", user_message))

        elif action == "REVIEW":
            result = self._execute_review(decision.get("task_for_agents", user_message))

        elif action == "TEST":
            result = self._execute_test(decision.get("task_for_agents", user_message))

        # GitHub actions
        elif action == "GITHUB_CLONE":
            result = self._execute_github_clone(decision.get("github_data", {}), user_message)

        elif action == "GITHUB_COMMIT":
            result = self._execute_github_commit(decision.get("github_data", {}), user_message)

        elif action == "GITHUB_PR":
            result = self._execute_github_pr(decision.get("github_data", {}), user_message)

        elif action == "GITHUB_STATUS":
            result = self._execute_github_status()

        elif action == "GITHUB_ISSUES":
            result = self._execute_github_issues(decision.get("github_data", {}))

        else:
            response = decision.get("response", "I didn't understand that. Can you rephrase?")
            result = {"type": "conversation", "response": response}

        # Save sessions after agent work
        if self.state.active_project_id:
            self._save_sessions(self.state.active_project_id)
            # Update file count
            files = self._list_project_files()
            self.db.touch_project(self.state.active_project_id, file_count=len(files))

        # Add to history
        self.state.messages.append({
            "role": "assistant",
            "content": json.dumps(result) if isinstance(result, dict) else str(result)
        })

        return result

    def _build_context(self) -> dict:
        """Build context dict for the router."""
        context = {
            "conversation_length": len(self.state.messages),
            "has_active_project": self.state.active_project_id is not None,
        }

        if self.state.active_project_id:
            context["active_project"] = self.state.active_project_name
            # Use project context for richer info
            context["project_summary"] = self.project_context.build_summary(
                self.state.active_project_id
            )

        # Include recent conversation for context
        if self.state.messages:
            recent = self.state.messages[-6:]
            context["recent_messages"] = [
                {"role": m["role"], "preview": m["content"][:200]}
                for m in recent
            ]

        return context

    # ==================== Execute Actions ====================

    def _get_project_context_str(self) -> str:
        """Get project context string for injection into agent prompts."""
        if self.state.active_project_id:
            return self.project_context.build_context(self.state.active_project_id)
        return ""

    def _execute_build(self, task: str) -> dict:
        """Execute full build pipeline: Plan → Code → Review → Test."""
        try:
            # Step 1: Planning
            self.emit("phase", "Planning")
            plan = self.planner.think_json(
                f"Create an implementation plan for: {task}"
            )

            if plan.get("error"):
                return {"type": "error", "error": "Failed to create plan"}

            self.state.project_plan = plan
            project_name = plan.get("project_name", "project")
            description = plan.get("summary", task[:200])
            self.emit("plan_ready", plan)

            # Set up project with persistence
            project_dir, project_id = self._setup_project(
                project_name, description=description, plan=plan
            )

            # Save plan to database
            self.db.update_project(project_id, plan_json=json.dumps(plan))

            # Step 2: Coding - Agent creates files directly via tools
            self.emit("phase", "Coding")
            tasks = plan.get("tasks", [])
            task_descriptions = "\n".join([
                f"{i+1}. {t.get('title', 'Task')}: {t.get('description', '')}"
                for i, t in enumerate(tasks)
            ])

            project_ctx = self._get_project_context_str()
            coding_prompt = f"""Implement this project in the current directory.

Project: {plan.get('summary', task)}
Tech stack: {json.dumps(plan.get('tech_stack', {}), indent=2)}

Tasks to implement:
{task_descriptions}

Files to create:
{json.dumps(plan.get('files_to_create', []), indent=2)}

Create ALL the files needed. Use the Write tool for each file."""

            code_response = self.coder.think(coding_prompt, context=project_ctx or None)

            # Step 3: Review - Coder↔Reviewer dialogue
            self.emit("phase", "Reviewing")
            review_response = run_code_review_dialogue(
                coder=self.coder,
                reviewer=self.reviewer,
                task="Review the project in the current directory. Check for bugs, security issues, and correctness.",
                emit=self.on_event,
                max_rounds=2
            )

            # Step 4: Testing - Tester↔Debugger dialogue
            self.emit("phase", "Testing")
            test_response = run_test_debug_dialogue(
                tester=self.tester,
                debugger=self.debugger,
                task="Write and run tests for the project in the current directory.",
                emit=self.on_event,
                max_rounds=2
            )

            # List files that were created
            created_files = self._list_project_files()

            # Update project in database
            self.db.touch_project(project_id, file_count=len(created_files))

            self.emit("build_complete", {
                "project": project_name,
                "files": created_files
            })

            return {
                "type": "build",
                "success": True,
                "project": project_name,
                "project_id": project_id,
                "project_dir": project_dir,
                "files": created_files,
                "plan": plan,
                "response": code_response[:500]
            }

        except Exception as e:
            self.emit("error", str(e))
            return {"type": "error", "error": str(e)}

    def _execute_code_only(self, task: str) -> dict:
        """Execute just the coder for a focused task."""
        self.emit("phase", "Coding")

        project_dir = self._ensure_project_dir()
        project_ctx = self._get_project_context_str()

        response = self.coder.think(task, context=project_ctx or None)
        created_files = self._list_project_files()

        return {
            "type": "code",
            "success": True,
            "response": response,
            "files": created_files,
            "project_dir": project_dir
        }

    def _execute_fix(self, task: str) -> dict:
        """Execute the debugger to fix an issue."""
        self.emit("phase", "Debugging")

        if not self.state.project_dir:
            self._ensure_project_dir()

        project_ctx = self._get_project_context_str()
        response = self.debugger.think(task, context=project_ctx or None)

        return {
            "type": "fix",
            "success": True,
            "response": response
        }

    def _execute_review(self, task: str) -> dict:
        """Execute the reviewer on code."""
        self.emit("phase", "Reviewing")

        if not self.state.project_dir:
            self._ensure_project_dir()

        project_ctx = self._get_project_context_str()
        response = self.reviewer.think(
            f"Review this code/project:\n{task}",
            context=project_ctx or None
        )

        return {
            "type": "review",
            "success": True,
            "response": response
        }

    def _execute_test(self, task: str) -> dict:
        """Execute the tester to write and run tests."""
        self.emit("phase", "Testing")

        if not self.state.project_dir:
            self._ensure_project_dir()

        project_ctx = self._get_project_context_str()
        response = self.tester.think(task, context=project_ctx or None)

        return {
            "type": "test",
            "success": True,
            "response": response
        }

    # ==================== Helpers ====================

    def _list_project_files(self) -> list[str]:
        """List files in the current project directory."""
        if not self.state.project_dir or not os.path.exists(self.state.project_dir):
            return []

        files = []
        try:
            for root, dirs, filenames in os.walk(self.state.project_dir):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules' and d != '__pycache__']
                for f in filenames:
                    if not f.startswith('.'):
                        rel = os.path.relpath(os.path.join(root, f), self.state.project_dir)
                        files.append(rel)
        except OSError:
            pass
        return files[:100]

    def clear(self):
        """Clear conversation and project state."""
        # Save sessions before clearing
        if self.state.active_project_id:
            self._save_sessions(self.state.active_project_id)

        self.state = ConversationState()
        self.router.clear_history()
        for agent in self._tool_agents:
            agent.clear_history()
        self.emit("cleared", {})

    # ==================== GitHub Actions ====================

    def _execute_github_clone(self, github_data: dict, user_message: str) -> dict:
        """Clone a GitHub repository."""
        self.emit("phase", "Cloning Repository")

        # Extract repo URL from github_data or user message
        repo_url = None
        if isinstance(github_data, dict):
            repo_url = github_data.get("repo_url") or github_data.get("repo")

        if not repo_url:
            # Try to extract from user message
            import re
            # Match github.com URLs or owner/repo format
            match = re.search(r'github\.com[/:]([^/\s]+/[^/\s]+?)(?:\.git)?(?:\s|$)', user_message)
            if match:
                repo_url = match.group(1)
            else:
                match = re.search(r'\b([a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+)\b', user_message)
                if match:
                    repo_url = match.group(1)

        if not repo_url:
            return {
                "type": "github",
                "action": "clone",
                "success": False,
                "error": "Could not find a repository URL. Try: 'clone owner/repo' or 'clone https://github.com/owner/repo'"
            }

        result = self.github.clone(repo_url)

        if result.success:
            # Set the cloned repo as the active project
            self.state.project_dir = result.output
            project_name = Path(result.output).name

            # Create project in database
            project_id = self.db.create_project(
                name=project_name,
                description=f"Cloned from {repo_url}",
                directory=result.output
            )
            self.state.active_project_id = project_id
            self.state.active_project_name = project_name

            # Set project dir for all agents
            for agent in self._tool_agents:
                agent.set_project_dir(result.output)

            self.emit("project_active", {
                "id": project_id,
                "name": project_name,
                "directory": result.output
            })

            return {
                "type": "github",
                "action": "clone",
                "success": True,
                "response": f"Cloned **{repo_url}** to `{result.output}`\n\nYou can now work on this project. Try asking me to make changes!",
                "project_dir": result.output,
                "project_id": project_id
            }

        return {
            "type": "github",
            "action": "clone",
            "success": False,
            "error": result.error or "Clone failed"
        }

    def _execute_github_commit(self, github_data: dict, user_message: str) -> dict:
        """Commit and push changes."""
        self.emit("phase", "Committing Changes")

        if not self.state.project_dir:
            return {
                "type": "github",
                "action": "commit",
                "success": False,
                "error": "No active project. Clone a repo first or open a project."
            }

        # Get commit message
        commit_message = None
        if isinstance(github_data, dict):
            commit_message = github_data.get("commit_message") or github_data.get("message")

        if not commit_message:
            # Generate a commit message based on changed files
            status = self.github.get_status_summary(self.state.project_dir)
            if status.success and status.output:
                lines = status.output.strip().split('\n')
                if len(lines) <= 3:
                    commit_message = f"Update {len(lines)} file(s)"
                else:
                    commit_message = f"Update {len(lines)} files"
            else:
                commit_message = "Update from Vibe Agents"

        result = self.github.commit_and_push(self.state.project_dir, commit_message)

        if result.success:
            return {
                "type": "github",
                "action": "commit",
                "success": True,
                "response": f"Committed and pushed: **{commit_message}**"
            }

        return {
            "type": "github",
            "action": "commit",
            "success": False,
            "error": result.error or "Commit failed"
        }

    def _execute_github_pr(self, github_data: dict, user_message: str) -> dict:
        """Create a pull request."""
        self.emit("phase", "Creating Pull Request")

        if not self.state.project_dir:
            return {
                "type": "github",
                "action": "pr",
                "success": False,
                "error": "No active project. Clone a repo first."
            }

        # Get PR details
        title = "Update from Vibe Agents"
        body = "Changes made via Vibe Agents AI coding platform."

        if isinstance(github_data, dict):
            title = github_data.get("pr_title") or github_data.get("title") or title
            body = github_data.get("pr_body") or github_data.get("body") or body

        # Get current branch
        branch_result = self.github.get_current_branch(self.state.project_dir)
        current_branch = branch_result.output if branch_result.success else "main"

        # If on main, create a feature branch first
        if current_branch in ("main", "master"):
            import time
            branch_name = f"vibe-agents-{int(time.time())}"
            self.github.create_branch(self.state.project_dir, branch_name)
            self.github.commit_and_push(self.state.project_dir, title)

        result = self.github.create_pr(
            self.state.project_dir,
            title=title,
            body=body
        )

        if result.success:
            return {
                "type": "github",
                "action": "pr",
                "success": True,
                "response": f"Created pull request!\n\n**{title}**\n\n{result.output}",
                "pr_url": result.output
            }

        return {
            "type": "github",
            "action": "pr",
            "success": False,
            "error": result.error or "Failed to create PR"
        }

    def _execute_github_status(self) -> dict:
        """Check git status of current project."""
        self.emit("phase", "Checking Status")

        if not self.state.project_dir:
            return {
                "type": "github",
                "action": "status",
                "success": False,
                "error": "No active project."
            }

        status = self.github.get_status_summary(self.state.project_dir)
        branch = self.github.get_current_branch(self.state.project_dir)

        if status.success:
            changes = status.output.strip() if status.output else "No changes"
            branch_name = branch.output if branch.success else "unknown"

            return {
                "type": "github",
                "action": "status",
                "success": True,
                "response": f"**Branch:** `{branch_name}`\n\n**Changes:**\n```\n{changes}\n```",
                "branch": branch_name,
                "changes": changes
            }

        return {
            "type": "github",
            "action": "status",
            "success": False,
            "error": status.error or "Failed to get status"
        }

    def _execute_github_issues(self, github_data: dict) -> dict:
        """List or view GitHub issues."""
        self.emit("phase", "Fetching Issues")

        if not self.state.project_dir:
            return {
                "type": "github",
                "action": "issues",
                "success": False,
                "error": "No active project."
            }

        issue_number = None
        if isinstance(github_data, dict):
            issue_number = github_data.get("issue_number") or github_data.get("number")

        if issue_number:
            result = self.github.get_issue(self.state.project_dir, int(issue_number))
        else:
            result = self.github.list_issues(self.state.project_dir)

        if result.success:
            try:
                data = json.loads(result.output)
                if isinstance(data, list):
                    if not data:
                        response = "No open issues found."
                    else:
                        lines = ["**Open Issues:**\n"]
                        for issue in data[:10]:
                            lines.append(f"- #{issue.get('number')}: {issue.get('title')}")
                        response = "\n".join(lines)
                else:
                    response = f"**Issue #{data.get('number')}:** {data.get('title')}\n\n{data.get('body', '')}"

                return {
                    "type": "github",
                    "action": "issues",
                    "success": True,
                    "response": response,
                    "data": data
                }
            except json.JSONDecodeError:
                return {
                    "type": "github",
                    "action": "issues",
                    "success": True,
                    "response": result.output
                }

        return {
            "type": "github",
            "action": "issues",
            "success": False,
            "error": result.error or "Failed to fetch issues"
        }
