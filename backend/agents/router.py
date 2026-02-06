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
        return """You are the Router for a multi-agent AI coding system.

CRITICAL: You MUST respond with ONLY a valid JSON object. No other text, no markdown, no explanation.

Classify the user's request and respond with this exact JSON structure:

{"action":"CONVERSATION","reasoning":"why","response":"your reply to user","task_for_agents":null,"confidence":0.9}

Actions:
- CONVERSATION: Greetings, questions, advice, discussion (include your response in "response" field)
- BUILD: Create complete applications ("Build me a...", "Create an app...")
- CODE_ONLY: Write specific code ("Write a function...", "Add a feature...")
- FIX: Debug errors ("This has an error...", "Why isn't this working...")
- REVIEW: Code review ("Review this code...", "Is this secure?")
- TEST: Write tests ("Write tests for...", "Test this code...")

Examples:

User: "Hello"
{"action":"CONVERSATION","reasoning":"Greeting","response":"Hello! I'm your AI coding assistant. What would you like to build today?","task_for_agents":null,"confidence":0.95}

User: "Build me a todo app"
{"action":"BUILD","reasoning":"Request for complete application","response":null,"task_for_agents":"Build a todo application with add, complete, and delete functionality","confidence":0.9}

User: "Write a function to validate emails"
{"action":"CODE_ONLY","reasoning":"Specific coding task","response":null,"task_for_agents":"Write a function to validate email addresses","confidence":0.85}

RESPOND WITH ONLY THE JSON OBJECT. NO OTHER TEXT."""

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
            decision = {
                "action": "CONVERSATION",
                "reasoning": "Defaulting to conversation",
                "response": "I'm not sure how to help with that. Could you rephrase?",
                "task_for_agents": None,
                "confidence": 0.3
            }

        # Handle case where we got raw text instead of JSON
        if "error" in decision and "raw" in decision:
            raw_text = decision.get("raw", "")
            # Use the raw text as the response - it's probably a valid conversational reply
            decision = {
                "action": "CONVERSATION",
                "reasoning": "Direct response",
                "response": raw_text,
                "task_for_agents": None,
                "confidence": 0.7
            }

        # Validate the decision has required fields
        if "action" not in decision:
            decision = {
                "action": "CONVERSATION",
                "reasoning": "Invalid routing decision",
                "response": decision.get("response", decision.get("raw", "Could you rephrase that?")),
                "task_for_agents": None,
                "confidence": 0.3
            }

        return decision
