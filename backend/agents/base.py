"""Base Agent class - all agents inherit from this.

Uses Claude Code CLI as backend - leverages your Claude Max subscription.
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable
import subprocess
import json
import os


class Agent(ABC):
    """
    Base class for all agents in the system.

    Uses the `claude` CLI in print mode to make requests.
    This uses your Claude Code Max subscription instead of API billing.
    """

    def __init__(
        self,
        name: str,
        role: str,
        model: str = "sonnet",  # CLI uses aliases: sonnet, opus, haiku
        on_message: Optional[Callable[[str, str, str], None]] = None
    ):
        self.name = name
        self.role = role
        self.model = model
        self.on_message = on_message  # Callback for UI updates
        self.conversation_history = []

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Each agent defines their own system prompt."""
        pass

    def emit(self, message_type: str, content: str):
        """Send a message to the UI."""
        if self.on_message:
            self.on_message(self.name, message_type, content)

    def think(self, task: str, context: Optional[dict] = None) -> str:
        """
        Process a task and return a response using Claude CLI.

        Args:
            task: The task or message to process
            context: Optional context (code, previous outputs, etc.)

        Returns:
            The agent's response
        """
        # Build the user message
        user_message = task
        if context:
            user_message = f"{task}\n\n## Context\n```\n{context}\n```"

        self.emit("thinking", f"Processing: {task[:100]}...")

        # Add to history (for context tracking)
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Build the full prompt including conversation history
        full_prompt = self._build_full_prompt(user_message)

        # Call Claude CLI
        try:
            result = subprocess.run(
                [
                    "claude",
                    "-p",  # Print mode (non-interactive)
                    "--model", self.model,
                    "--system-prompt", self.system_prompt,
                    "--dangerously-skip-permissions",  # No tool use, just text
                    "--tools", "",  # Disable all tools - pure text generation
                    full_prompt
                ],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                cwd=os.path.expanduser("~")  # Run from home to avoid project context
            )

            if result.returncode != 0:
                error_msg = result.stderr or "Unknown CLI error"
                self.emit("error", error_msg)
                raise RuntimeError(f"Claude CLI failed: {error_msg}")

            assistant_message = result.stdout.strip()

        except subprocess.TimeoutExpired:
            self.emit("error", "Request timed out")
            raise RuntimeError("Claude CLI request timed out")
        except FileNotFoundError:
            self.emit("error", "Claude CLI not found - is it installed?")
            raise RuntimeError("Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code")

        # Add response to history
        self.conversation_history.append({
            "role": "assistant",
            "content": assistant_message
        })

        self.emit("response", assistant_message)

        return assistant_message

    def _build_full_prompt(self, current_message: str) -> str:
        """
        Build a prompt that includes relevant conversation history.
        For multi-turn context, we include previous exchanges.
        """
        if len(self.conversation_history) <= 1:
            return current_message

        # Include last few exchanges for context (not the current one)
        history_parts = []
        for msg in self.conversation_history[:-1]:  # Exclude current message
            role = "User" if msg["role"] == "user" else "Assistant"
            content = msg["content"]
            # Truncate long history entries
            if len(content) > 2000:
                content = content[:2000] + "... [truncated]"
            history_parts.append(f"{role}: {content}")

        if history_parts:
            history_text = "\n\n".join(history_parts)
            return f"""Previous conversation:
{history_text}

Current request:
{current_message}"""

        return current_message

    def clear_history(self):
        """Clear conversation history for a fresh start."""
        self.conversation_history = []
