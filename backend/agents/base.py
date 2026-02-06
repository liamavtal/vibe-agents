"""Base Agent class - all agents inherit from this.

Uses Claude Code CLI as backend - leverages your Claude Max subscription.
Supports real-time streaming output and per-agent tool access.
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable, Any
import subprocess
import json
import os
import re

from backend import get_claude_cli


class Agent(ABC):
    """
    Base class for all agents in the system.

    Uses the `claude` CLI with:
    - Streaming output (--output-format stream-json)
    - Per-agent tool permissions (--allowedTools)
    - Project directory access (cwd + --add-dir)
    - Session persistence (--session-id)
    """

    def __init__(
        self,
        name: str,
        role: str,
        model: str = "sonnet",
        on_message: Optional[Callable[[str, str, Any], None]] = None
    ):
        self.name = name
        self.role = role
        self.model = model
        self.on_message = on_message
        self._session_id: Optional[str] = None
        self._project_dir: Optional[str] = None

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Each agent defines their own system prompt."""
        pass

    @property
    @abstractmethod
    def allowed_tools(self) -> list[str]:
        """Each agent defines which tools they can use.

        Return empty list to disable all tools (text-only mode).
        Return tool names for specific access, e.g. ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]
        """
        pass

    def set_project_dir(self, path: str):
        """Set the project directory this agent can access."""
        self._project_dir = os.path.abspath(path)

    def set_session_id(self, session_id: str):
        """Set session ID for conversation persistence across calls."""
        self._session_id = session_id

    def emit(self, message_type: str, content: Any):
        """Send a message/event to the UI."""
        if self.on_message:
            self.on_message(self.name, message_type, content)

    def think(self, task: str, context: Optional[str] = None) -> str:
        """
        Process a task using Claude CLI with streaming output.

        For agents with tools, file operations happen directly during this call.
        Events are streamed to the UI in real-time via the emit callback.

        Args:
            task: The task or message to process
            context: Optional context string

        Returns:
            The agent's final response text
        """
        prompt = task
        if context:
            prompt = f"{task}\n\n## Context\n{context}"

        self.emit("thinking", f"Processing: {task[:100]}...")

        args = self._build_streaming_args(prompt)

        try:
            result_text = self._run_streaming(args)
        except FileNotFoundError:
            self.emit("error", "Claude CLI not found - is it installed?")
            raise RuntimeError(
                "Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
            )
        except subprocess.TimeoutExpired:
            self.emit("error", "Request timed out")
            raise RuntimeError("Claude CLI timed out after 5 minutes")

        self.emit("done", result_text[:200])
        return result_text

    def think_json(self, task: str, context: Optional[str] = None) -> dict:
        """
        Process a task and return parsed JSON output.

        Used by Router (routing decisions) and Planner (structured plans).
        Runs without tools - pure text generation parsed as JSON.

        Args:
            task: The task to process
            context: Optional context string

        Returns:
            Parsed JSON dict from the agent's response
        """
        prompt = task
        if context:
            prompt = f"{task}\n\n## Context\n{context}"

        self.emit("thinking", f"Analyzing: {task[:100]}...")

        args = self._build_json_args(prompt)
        cwd = self._project_dir or os.path.expanduser("~")

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=cwd,
                env={**os.environ}
            )
        except FileNotFoundError:
            self.emit("error", "Claude CLI not found")
            raise RuntimeError(
                "Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
            )
        except subprocess.TimeoutExpired:
            self.emit("error", "Request timed out")
            raise RuntimeError("Claude CLI timed out")

        if result.returncode != 0:
            error = result.stderr or "Unknown error"
            self.emit("error", error[:500])
            raise RuntimeError(f"Claude CLI failed: {error[:500]}")

        output = result.stdout.strip()
        parsed = self._parse_json_output(output)
        self.emit("done", json.dumps(parsed, indent=2)[:200])
        return parsed

    def _build_streaming_args(self, prompt: str) -> list[str]:
        """Build CLI args for streaming mode (agents with tool access)."""
        args = [
            get_claude_cli(), "-p", prompt,
            "--verbose",
            "--output-format", "stream-json",
            "--model", self.model,
            "--system-prompt", self.system_prompt,
        ]
        self._add_tool_args(args)
        self._add_common_args(args)
        return args

    def _build_json_args(self, prompt: str) -> list[str]:
        """Build CLI args for JSON output mode (text-only structured output)."""
        args = [
            get_claude_cli(), "-p", prompt,
            "--model", self.model,
            "--system-prompt", self.system_prompt,
            "--tools", "",
        ]
        self._add_common_args(args)
        return args

    def _add_tool_args(self, args: list[str]):
        """Add tool permission flags based on agent's allowed_tools."""
        tools = self.allowed_tools
        if not tools:
            # Disable all tools - text-only mode
            args.extend(["--tools", ""])
        else:
            # Enable tools with permission bypass + whitelist
            args.append("--dangerously-skip-permissions")
            args.extend(["--allowedTools", ",".join(tools)])

    def _add_common_args(self, args: list[str]):
        """Add project dir and session args."""
        if self._project_dir:
            args.extend(["--add-dir", self._project_dir])
        if self._session_id:
            args.extend(["--session-id", self._session_id])

    def _run_streaming(self, args: list[str]) -> str:
        """
        Run Claude CLI and stream events in real-time.

        Parses stream-json output line by line, computes text deltas,
        detects tool use events, and forwards everything to the UI.

        Returns the final result text.
        """
        cwd = self._project_dir or os.path.expanduser("~")

        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env={**os.environ}
        )

        result_text = ""
        current_msg_id = None
        emitted_text_len = 0
        seen_tool_ids = set()

        try:
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")

                if event_type == "system":
                    # System init - capture session ID
                    sid = event.get("session_id")
                    if sid:
                        self._session_id = sid

                elif event_type == "assistant":
                    msg = event.get("message", {})
                    msg_id = msg.get("id", "")
                    blocks = msg.get("content", [])

                    # Reset text tracking on new message (new turn after tool use)
                    if msg_id and msg_id != current_msg_id:
                        current_msg_id = msg_id
                        emitted_text_len = 0

                    # Compute and emit text deltas
                    all_text = "\n".join(
                        b.get("text", "") for b in blocks
                        if b.get("type") == "text"
                    )
                    if len(all_text) > emitted_text_len:
                        delta = all_text[emitted_text_len:]
                        self.emit("streaming", delta)
                        emitted_text_len = len(all_text)

                    # Emit new tool use events
                    for block in blocks:
                        if block.get("type") == "tool_use":
                            tid = block.get("id", "")
                            if tid and tid not in seen_tool_ids:
                                seen_tool_ids.add(tid)
                                self.emit("tool_use", {
                                    "tool": block.get("name", ""),
                                    "input": self._summarize_tool_input(
                                        block.get("name", ""),
                                        block.get("input", {})
                                    )
                                })

                elif event_type == "result":
                    result_text = event.get("result", "")
                    sid = event.get("session_id")
                    if sid:
                        self._session_id = sid
                    cost = event.get("cost_usd")
                    if cost is not None:
                        self.emit("cost", {
                            "cost_usd": cost,
                            "duration_ms": event.get("duration_ms", 0)
                        })

            process.wait(timeout=300)

            if process.returncode != 0 and not result_text:
                stderr = process.stderr.read() if process.stderr else ""
                if stderr:
                    self.emit("error", stderr[:500])
                    raise RuntimeError(f"CLI error: {stderr[:500]}")

            return result_text

        except Exception:
            if process.poll() is None:
                process.kill()
            raise
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

    def _summarize_tool_input(self, tool: str, input_data: dict) -> dict:
        """Create a UI-friendly summary of tool input."""
        if tool == "Read":
            return {"file": input_data.get("file_path", "?")}
        elif tool in ("Write", "Edit"):
            path = input_data.get("file_path", "?")
            content = str(input_data.get("content", input_data.get("new_string", "")))
            return {"file": path, "size": len(content)}
        elif tool == "Bash":
            return {"command": input_data.get("command", "")[:200]}
        elif tool == "Glob":
            return {"pattern": input_data.get("pattern", "")}
        elif tool == "Grep":
            return {"pattern": input_data.get("pattern", "")}
        return {k: str(v)[:100] for k, v in list(input_data.items())[:3]}

    def _parse_json_output(self, output: str) -> dict:
        """Parse JSON from CLI output, handling multiple formats."""
        # Try 1: Direct JSON parse
        try:
            parsed = json.loads(output)
            if isinstance(parsed, dict):
                # If it's a CLI wrapper with "result" field, extract it
                if "result" in parsed and "type" in parsed:
                    result_str = parsed["result"]
                    if isinstance(result_str, dict):
                        return result_str
                    if isinstance(result_str, str):
                        try:
                            return json.loads(result_str)
                        except json.JSONDecodeError:
                            return self._extract_json_from_text(result_str)
                return parsed
        except json.JSONDecodeError:
            pass

        # Try 2: Extract from text (might have markdown wrapping)
        return self._extract_json_from_text(output)

    def _extract_json_from_text(self, text: str) -> dict:
        """Extract JSON from text that might contain markdown code blocks."""
        # Try ```json blocks
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding a JSON object
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # Last resort - return error dict
        self.emit("warning", f"Could not parse JSON from output: {text[:200]}")
        return {
            "error": "Failed to parse structured output",
            "raw": text[:500]
        }

    def clear_history(self):
        """Clear session for a fresh start."""
        self._session_id = None
