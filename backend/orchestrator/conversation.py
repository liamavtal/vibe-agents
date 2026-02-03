"""
Conversational Orchestrator - Smart agent routing based on user intent.

This is what makes Vibe Agents work like Claude Code:
1. You chat naturally
2. The Router analyzes your message
3. It decides which agents (if any) to use
4. You get a response

No more "enter prompt → run all agents → wait".
Instead: natural conversation with smart agent activation.
"""

import json
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
from ..sandbox import Sandbox


@dataclass
class ConversationState:
    """Tracks the ongoing conversation and any active project."""
    messages: list = field(default_factory=list)  # Chat history
    active_project: Optional[str] = None
    project_files: dict = field(default_factory=dict)
    project_plan: Optional[dict] = None


class ConversationalOrchestrator:
    """
    The conversational interface to the multi-agent system.

    Unlike the pipeline-based Orchestrator, this one:
    - Maintains conversation state
    - Routes messages through the Router agent
    - Invokes specialized agents only when needed
    - Supports natural back-and-forth dialogue
    """

    def __init__(
        self,
        projects_dir: str = "./projects",
        on_event: Optional[Callable[[str, Any], None]] = None
    ):
        self.projects_dir = projects_dir
        self.on_event = on_event
        self.state = ConversationState()
        self.sandbox: Optional[Sandbox] = None

        # Initialize agents
        agent_callback = self._create_agent_callback()
        self.router = RouterAgent(on_message=agent_callback)
        self.planner = PlannerAgent(on_message=agent_callback)
        self.coder = CoderAgent(on_message=agent_callback)
        self.reviewer = ReviewerAgent(on_message=agent_callback)
        self.tester = TesterAgent(on_message=agent_callback)
        self.debugger = DebuggerAgent(on_message=agent_callback)

    def _create_agent_callback(self) -> Callable:
        """Route agent messages to the UI."""
        def callback(agent_name: str, msg_type: str, content: str):
            self.emit("agent_message", {
                "agent": agent_name,
                "type": msg_type,
                "content": content
            })
        return callback

    def emit(self, event_type: str, data: Any):
        """Emit an event to the UI."""
        if self.on_event:
            self.on_event(event_type, data)

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

        else:
            # Unknown action - respond conversationally
            response = decision.get("response", "I didn't understand that action. Can you rephrase?")
            result = {"type": "conversation", "response": response}

        # Add assistant response to history
        self.state.messages.append({
            "role": "assistant",
            "content": json.dumps(result) if isinstance(result, dict) else str(result)
        })

        return result

    def _build_context(self) -> dict:
        """Build context dict for the router."""
        context = {
            "conversation_length": len(self.state.messages),
            "has_active_project": self.state.active_project is not None,
        }

        if self.state.active_project:
            context["active_project"] = self.state.active_project
            context["project_files"] = list(self.state.project_files.keys())

        # Include recent conversation for context
        if len(self.state.messages) > 0:
            recent = self.state.messages[-6:]  # Last 3 exchanges
            context["recent_messages"] = [
                {"role": m["role"], "preview": m["content"][:200]}
                for m in recent
            ]

        return context

    def _execute_build(self, task: str) -> dict:
        """Execute full build pipeline: Plan → Code → Verify → Review → Test."""
        self.emit("phase", "Planning")

        # Setup sandbox
        self.sandbox = Sandbox(timeout=30)

        try:
            # Step 1: Planning
            plan_response = self.planner.think(
                f"Create an implementation plan for: {task}"
            )
            plan = self._extract_json(plan_response)

            if not plan:
                return {"type": "error", "error": "Failed to create plan"}

            self.state.project_plan = plan
            self.state.active_project = plan.get("project_name", "project")
            self.emit("plan_ready", plan)

            # Step 2: Coding
            self.emit("phase", "Coding")
            tasks = plan.get("tasks", [])

            for i, task_item in enumerate(tasks):
                self.emit("task_start", {
                    "task_number": i + 1,
                    "total": len(tasks),
                    "title": task_item.get("title", "Task")
                })

                context = {
                    "task": task_item,
                    "existing_files": self.state.project_files,
                    "tech_stack": plan.get("tech_stack", {})
                }

                code_response = self.coder.think(
                    f"Implement: {json.dumps(task_item, indent=2)}",
                    context=json.dumps(context, indent=2)
                )

                code_output = self._extract_json(code_response)
                if code_output and "code" in code_output:
                    file_path = code_output.get("file_path", f"file_{i}.py")
                    self.state.project_files[file_path] = code_output["code"]
                    self.emit("file_created", {"path": file_path})

            # Step 3: Verification
            self.emit("phase", "Verifying")
            self.sandbox.setup(self.state.active_project)
            self.sandbox.write_files(self.state.project_files)

            main_file = self._find_main_file()
            if main_file:
                result = self.sandbox.run_python(main_file)
                self.emit("execution_result", {
                    "success": result.success,
                    "stdout": result.stdout[:500],
                    "stderr": result.stderr[:500]
                })

                # Debug if failed
                if not result.success and result.stderr:
                    self.emit("phase", "Debugging")
                    self._debug_code(result.stderr)

            # Step 4: Review
            self.emit("phase", "Reviewing")
            all_code = "\n\n".join([
                f"# File: {p}\n{c}"
                for p, c in self.state.project_files.items()
            ])
            review_response = self.reviewer.think(
                "Review this code:",
                context=all_code
            )
            review = self._extract_json(review_response)
            if review:
                self.emit("review_complete", review)

            # Step 5: Testing
            self.emit("phase", "Testing")
            test_response = self.tester.think(
                "Write tests:",
                context=json.dumps({
                    "files": self.state.project_files,
                    "plan": plan
                }, indent=2)
            )
            test_output = self._extract_json(test_response)
            if test_output and "code" in test_output:
                test_path = test_output.get("file_path", "test_main.py")
                self.emit("test_created", {"path": test_path})

            self.emit("build_complete", {
                "project": self.state.active_project,
                "files": list(self.state.project_files.keys())
            })

            return {
                "type": "build",
                "success": True,
                "project": self.state.active_project,
                "files": list(self.state.project_files.keys()),
                "plan": plan
            }

        except Exception as e:
            self.emit("error", str(e))
            return {"type": "error", "error": str(e)}

        finally:
            if self.sandbox:
                self.sandbox.cleanup()

    def _execute_code_only(self, task: str) -> dict:
        """Execute just the coder for a focused task."""
        self.emit("phase", "Coding")

        context = {
            "existing_files": self.state.project_files,
            "focused_task": True
        }

        response = self.coder.think(task, context=json.dumps(context, indent=2))
        code_output = self._extract_json(response)

        if code_output and "code" in code_output:
            file_path = code_output.get("file_path", "output.py")
            self.state.project_files[file_path] = code_output["code"]
            self.emit("file_created", {
                "path": file_path,
                "explanation": code_output.get("explanation", "")
            })

            return {
                "type": "code",
                "success": True,
                "file_path": file_path,
                "code": code_output["code"],
                "explanation": code_output.get("explanation", "")
            }

        return {
            "type": "code",
            "success": False,
            "raw_response": response
        }

    def _execute_fix(self, task: str) -> dict:
        """Execute the debugger to fix an issue."""
        self.emit("phase", "Debugging")

        context = {
            "files": self.state.project_files,
            "error_context": task
        }

        response = self.debugger.think(task, context=json.dumps(context, indent=2))
        fix = self._extract_json(response)

        if fix:
            self.emit("fix_suggested", fix)

            # Apply fix if provided
            if fix.get("file_path") and fix.get("fix", {}).get("new_code"):
                file_path = fix["file_path"]
                new_code = fix["fix"]["new_code"]

                if len(new_code) > 100:
                    self.state.project_files[file_path] = new_code
                else:
                    old_code = fix["fix"].get("old_code", "")
                    if old_code and file_path in self.state.project_files:
                        self.state.project_files[file_path] = \
                            self.state.project_files[file_path].replace(old_code, new_code)

                self.emit("fix_applied", {"file": file_path})

            return {
                "type": "fix",
                "success": True,
                "diagnosis": fix.get("diagnosis", ""),
                "fix": fix.get("fix", {})
            }

        return {
            "type": "fix",
            "success": False,
            "raw_response": response
        }

    def _execute_review(self, task: str) -> dict:
        """Execute the reviewer on code."""
        self.emit("phase", "Reviewing")

        # If no specific code provided, review current project files
        context = task
        if not context or len(context) < 50:
            context = "\n\n".join([
                f"# File: {p}\n{c}"
                for p, c in self.state.project_files.items()
            ])

        response = self.reviewer.think("Review this code:", context=context)
        review = self._extract_json(response)

        if review:
            self.emit("review_complete", review)
            return {
                "type": "review",
                "success": True,
                "verdict": review.get("verdict", ""),
                "issues": review.get("issues", []),
                "summary": review.get("summary", "")
            }

        return {
            "type": "review",
            "success": False,
            "raw_response": response
        }

    def _execute_test(self, task: str) -> dict:
        """Execute the tester to write tests."""
        self.emit("phase", "Testing")

        context = {
            "files": self.state.project_files,
            "test_request": task
        }

        response = self.tester.think(task, context=json.dumps(context, indent=2))
        test_output = self._extract_json(response)

        if test_output and "code" in test_output:
            test_path = test_output.get("file_path", "test_main.py")
            self.emit("test_created", {"path": test_path})

            return {
                "type": "test",
                "success": True,
                "file_path": test_path,
                "code": test_output["code"],
                "description": test_output.get("description", "")
            }

        return {
            "type": "test",
            "success": False,
            "raw_response": response
        }

    def _debug_code(self, error: str, max_attempts: int = 3):
        """Attempt to fix code errors."""
        for attempt in range(max_attempts):
            self.emit("debug_attempt", {"attempt": attempt + 1, "max": max_attempts})

            response = self.debugger.think(
                f"Fix this error:\n{error}",
                context=json.dumps({"files": self.state.project_files}, indent=2)
            )

            fix = self._extract_json(response)
            if not fix:
                continue

            file_path = fix.get("file_path")
            if file_path and fix.get("fix", {}).get("new_code"):
                new_code = fix["fix"]["new_code"]
                self.state.project_files[file_path] = new_code
                self.sandbox.write_file(file_path, new_code)

                result = self.sandbox.run_python(file_path)
                if result.success:
                    self.emit("debug_success", "Fixed!")
                    return
                error = result.stderr

        self.emit("debug_exhausted", f"Could not fix after {max_attempts} attempts")

    def _find_main_file(self) -> Optional[str]:
        """Find the main entry point."""
        for name in ["main.py", "app.py", "run.py", "__main__.py"]:
            if name in self.state.project_files:
                return name
        if self.state.project_files:
            return list(self.state.project_files.keys())[0]
        return None

    def _extract_json(self, text: str) -> Optional[dict]:
        """Extract JSON from response text."""
        import re

        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        brace_match = re.search(r'\{.*\}', text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def clear(self):
        """Clear conversation and project state."""
        self.state = ConversationState()
        self.router.clear_history()
        self.emit("cleared", {})
