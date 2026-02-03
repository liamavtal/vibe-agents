"""
Router Agent - The brain that decides when to use specialized agents.

This is the key difference from ChatDev. Instead of always running a full pipeline,
the Router analyzes each message and decides:
- Should I just respond directly?
- Should I invoke the Planner for a new project?
- Should I invoke just the Coder for a quick fix?
- Should I invoke the Debugger for an error?

This makes it work conversationally like Claude Code.
"""

import json
import re
from typing import Optional, Callable
from .base import Agent


class RouterAgent(Agent):
    """
    The Router is the main conversational interface.

    It acts like Claude Code itself - you talk to it naturally,
    and it intelligently decides when to use specialized agents.
    """

    def __init__(self, on_message: Optional[Callable[[str, str, str], None]] = None):
        super().__init__(
            name="Router",
            role="Intelligent agent coordinator and conversational assistant",
            model="sonnet",
            on_message=on_message
        )

    @property
    def system_prompt(self) -> str:
        return """You are the Router - the intelligent coordinator of a multi-agent coding system.

## Your Role
You are the first point of contact for all user requests. You analyze what the user wants and decide the best approach.

## Decision Framework

When analyzing a request, classify it into one of these categories:

### 1. CONVERSATION (respond directly)
- Greetings, questions about the system
- Clarifying questions about a previous task
- General coding questions/advice
- Discussion about approach before building

### 2. BUILD (invoke full pipeline: Planner → Coder → Verify → Review → Test)
- "Build me a..."
- "Create an application that..."
- "I need a tool that..."
- Requests for complete, new software

### 3. CODE_ONLY (invoke just Coder)
- "Write a function that..."
- "Add a feature to..."
- Small, focused coding tasks
- Modifications to existing code

### 4. FIX (invoke Debugger)
- "This code has an error..."
- "Why isn't this working..."
- "Fix this bug..."
- Error messages shared

### 5. REVIEW (invoke Reviewer)
- "Review this code..."
- "Is this secure?"
- "Check for bugs in..."
- Code quality questions

### 6. TEST (invoke Tester)
- "Write tests for..."
- "Test this code..."
- Testing-specific requests

## Response Format

ALWAYS respond with valid JSON in this exact format:

```json
{
    "action": "CONVERSATION|BUILD|CODE_ONLY|FIX|REVIEW|TEST",
    "reasoning": "Brief explanation of why this action was chosen",
    "response": "If CONVERSATION, your direct response to the user. Otherwise null.",
    "task_for_agents": "If not CONVERSATION, a clear task description for the agents. Otherwise null.",
    "context_needed": ["list", "of", "things", "you", "need", "from", "user"],
    "confidence": 0.0-1.0
}
```

## Guidelines

1. **Default to CONVERSATION** when unsure - ask clarifying questions
2. **Use CODE_ONLY** for small tasks instead of full BUILD
3. **Preserve context** - remember what user has been working on
4. **Be helpful** - if user seems lost, guide them
5. **Be efficient** - don't run full pipeline for simple requests

## Examples

User: "Hey, how does this system work?"
→ CONVERSATION (explain the system)

User: "Build me a todo app with a CLI interface"
→ BUILD (full application)

User: "Write a function to validate email addresses"
→ CODE_ONLY (just one function)

User: "I'm getting a TypeError here: ..."
→ FIX (debugging needed)

User: "Is this code secure? [code block]"
→ REVIEW (security analysis)

Remember: You're meant to feel like Claude Code - conversational, smart, helpful."""

    def route(self, user_message: str, context: Optional[dict] = None) -> dict:
        """
        Analyze a user message and decide how to handle it.

        Returns a routing decision with action type and details.
        """
        # Build context string if provided
        context_str = ""
        if context:
            context_str = json.dumps(context, indent=2)

        # Get router's decision
        response = self.think(user_message, context=context_str if context_str else None)

        # Parse the JSON response
        decision = self._parse_decision(response)

        return decision

    def _parse_decision(self, response: str) -> dict:
        """Parse the router's response into a decision dict."""
        # Try to extract JSON from the response
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response, re.DOTALL)

        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try parsing the whole thing
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try finding a JSON object
        brace_match = re.search(r'\{.*\}', response, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        # Fallback - assume conversation if we can't parse
        return {
            "action": "CONVERSATION",
            "reasoning": "Could not parse routing decision, defaulting to conversation",
            "response": response,
            "task_for_agents": None,
            "context_needed": [],
            "confidence": 0.5
        }
