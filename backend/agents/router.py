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

### 7. GITHUB_CLONE (clone a repository)
- "Clone this repo..."
- "Get the code from github.com/..."
- "Pull down the X repository"
- Extract the repo URL or owner/repo from the message

### 8. GITHUB_COMMIT (commit and push changes)
- "Commit these changes"
- "Push my changes"
- "Save and push to GitHub"
- Extract a commit message from context or generate one

### 9. GITHUB_PR (create a pull request)
- "Create a PR"
- "Open a pull request"
- "Submit this for review"
- Extract PR title and description from context

### 10. GITHUB_STATUS (check repository status)
- "What's the git status?"
- "Show me what's changed"
- "Any uncommitted changes?"

### 11. GITHUB_ISSUES (list or view issues)
- "Show me the issues"
- "What issues are open?"
- "Look at issue #X"

## Response Format

ALWAYS respond with ONLY valid JSON (no markdown, no explanation outside the JSON):

{
    "action": "CONVERSATION|BUILD|CODE_ONLY|FIX|REVIEW|TEST|GITHUB_CLONE|GITHUB_COMMIT|GITHUB_PR|GITHUB_STATUS|GITHUB_ISSUES",
    "reasoning": "Brief explanation of why this action was chosen",
    "response": "If CONVERSATION, your direct response to the user. Otherwise null.",
    "task_for_agents": "If not CONVERSATION, a clear task description for the agents. Otherwise null.",
    "github_data": "For GITHUB_* actions, include relevant data: {repo_url, commit_message, pr_title, pr_body, issue_number}. Otherwise null.",
    "confidence": 0.0-1.0
}

## Guidelines
1. Default to CONVERSATION when unsure
2. Use CODE_ONLY for small tasks instead of full BUILD
3. Be efficient - don't run full pipeline for simple requests
4. For GITHUB_* actions, extract relevant info (URLs, messages, etc.) into github_data
5. Output ONLY the JSON object - no other text"""

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

        # Handle case where we got raw text instead of JSON
        if "error" in decision and "raw" in decision:
            raw_text = decision.get("raw", "")
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
                "reasoning": "Invalid routing decision, defaulting to conversation",
                "response": decision.get("response", decision.get("raw", "Could you rephrase that?")),
                "task_for_agents": None,
                "confidence": 0.3
            }

        return decision
