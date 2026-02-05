"""
Router Agent - The brain that decides when to use specialized agents.

Analyzes each message and decides:
- Should I just respond directly? (CONVERSATION)
- Should I invoke the full pipeline? (BUILD)
- Should I invoke just the Coder? (CODE_ONLY)
- Should I invoke the Debugger? (FIX)
- Should I invoke the Reviewer? (REVIEW)
- Should I invoke the Tester? (TEST)

Uses think_json() for guaranteed structured routing decisions.
"""

import json
from typing import Optional, Callable, Any
from .base import Agent


class RouterAgent(Agent):
    """
    The Router is the main conversational interface.

    Analyzes user intent and routes to the right agents.
    Uses structured JSON output (no tools needed).
    """

    def __init__(self, on_message: Optional[Callable[[str, str, Any], None]] = None):
        super().__init__(
            name="Router",
            role="Intelligent agent coordinator and conversational assistant",
            model="sonnet",
            on_message=on_message
        )

    @property
    def allowed_tools(self) -> list[str]:
        return []  # Text-only - no tool access

    @property
    def system_prompt(self) -> str:
        return """You are the Router - the intelligent coordinator of a multi-agent coding system.

## Your Role
You analyze user requests and decide the best approach. You are the FIRST point of contact.

## Decision Framework

Classify each request into one of these categories:

### 1. CONVERSATION (respond directly)
- Greetings, questions about the system
- Clarifying questions about a previous task
- General coding questions/advice
- Discussion about approach before building

### 2. BUILD (invoke full pipeline: Planner → Coder → Verify → Review → Test)
- "Build me a..."
- "Create an application that..."
- Requests for complete, new software

### 3. CODE_ONLY (invoke just Coder)
- "Write a function that..."
- "Add a feature to..."
- Small, focused coding tasks

### 4. FIX (invoke Debugger)
- "This code has an error..."
- "Why isn't this working..."
- Error messages shared

### 5. REVIEW (invoke Reviewer)
- "Review this code..."
- "Is this secure?"
- Code quality questions

### 6. TEST (invoke Tester)
- "Write tests for..."
- "Test this code..."

## Response Format

ALWAYS respond with ONLY valid JSON (no markdown, no explanation outside the JSON):

{
    "action": "CONVERSATION|BUILD|CODE_ONLY|FIX|REVIEW|TEST",
    "reasoning": "Brief explanation of why this action was chosen",
    "response": "If CONVERSATION, your direct response to the user. Otherwise null.",
    "task_for_agents": "If not CONVERSATION, a clear task description for the agents. Otherwise null.",
    "confidence": 0.0-1.0
}

## Guidelines
1. Default to CONVERSATION when unsure
2. Use CODE_ONLY for small tasks instead of full BUILD
3. Be efficient - don't run full pipeline for simple requests
4. Output ONLY the JSON object - no other text"""

    def route(self, user_message: str, context: Optional[dict] = None) -> dict:
        """
        Analyze a user message and decide how to handle it.

        Returns a routing decision dict with action type and details.
        """
        context_str = json.dumps(context, indent=2) if context else None

        try:
            decision = self.think_json(user_message, context=context_str)
        except Exception as e:
            # If JSON parsing fails completely, default to conversation
            self.emit("warning", f"Router fallback: {e}")
            decision = {
                "action": "CONVERSATION",
                "reasoning": "Router could not process, defaulting to conversation",
                "response": "I'm not sure how to help with that. Could you rephrase?",
                "task_for_agents": None,
                "confidence": 0.3
            }

        # Validate the decision has required fields
        if "action" not in decision or decision.get("error"):
            decision = {
                "action": "CONVERSATION",
                "reasoning": "Invalid routing decision, defaulting to conversation",
                "response": decision.get("raw", "Could you rephrase that?"),
                "task_for_agents": None,
                "confidence": 0.3
            }

        return decision
