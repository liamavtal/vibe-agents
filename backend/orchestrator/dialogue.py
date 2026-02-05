"""
DialogueRound - Agent-to-agent visible discussion system.

Makes agents respond to each other's output so the user can see
the collaboration happening in real-time:
- Reviewer critiques Coder's work, Coder revises
- Tester reports failures, Debugger fixes them
- Each agent sees the previous agents' output in the round

The UI shows dialogue dividers and agent chat bubbles for each exchange.
"""

from typing import Optional, Callable, Any
from dataclasses import dataclass, field


@dataclass
class DialogueEntry:
    """A single entry in a dialogue round."""
    agent_name: str
    content: str
    role: str = ""


@dataclass
class DialogueRound:
    """
    A round of agent-to-agent discussion.

    Each round has a topic, a sequence of agent exchanges, and emits
    events to the UI so the user sees the back-and-forth.
    """
    topic: str
    entries: list = field(default_factory=list)
    max_exchanges: int = 4
    emit: Optional[Callable[[str, Any], None]] = None

    def add(self, agent_name: str, content: str, role: str = ""):
        """Record an agent's contribution to the dialogue."""
        self.entries.append(DialogueEntry(
            agent_name=agent_name,
            content=content,
            role=role
        ))

    def get_context(self, for_agent: str = "") -> str:
        """
        Build context string from all previous entries in this round.

        Each agent sees what came before it, formatted as a readable
        conversation transcript.
        """
        if not self.entries:
            return ""

        parts = [f"## Ongoing Discussion: {self.topic}\n"]
        for entry in self.entries:
            parts.append(f"**{entry.agent_name}** ({entry.role}):\n{entry.content}\n")

        if for_agent:
            parts.append(f"\nNow it's your turn, {for_agent}. "
                        "Respond to the discussion above.")

        return "\n".join(parts)

    @property
    def exchange_count(self) -> int:
        return len(self.entries)

    @property
    def at_limit(self) -> bool:
        return self.exchange_count >= self.max_exchanges

    @property
    def last_entry(self) -> Optional[DialogueEntry]:
        return self.entries[-1] if self.entries else None


def run_code_review_dialogue(
    coder,
    reviewer,
    task: str,
    emit: Optional[Callable[[str, Any], None]] = None,
    max_rounds: int = 2
) -> str:
    """
    Run a Coder ↔ Reviewer dialogue.

    Flow:
    1. Coder implements the task
    2. Reviewer critiques the code
    3. If issues found and rounds remain, Coder revises
    4. Repeat until approved or max rounds reached

    Returns the final coder response.
    """
    dialogue = DialogueRound(
        topic=f"Code Review: {task[:100]}",
        max_exchanges=max_rounds * 2,
        emit=emit
    )

    if emit:
        emit("dialogue_start", {"topic": dialogue.topic, "agents": ["Coder", "Reviewer"]})

    # Initial coding
    code_response = coder.think(task)
    dialogue.add("Coder", code_response, "Developer")

    for round_num in range(max_rounds):
        if dialogue.at_limit:
            break

        # Reviewer critiques
        if emit:
            emit("dialogue_exchange", {
                "round": round_num + 1,
                "from": "Coder",
                "to": "Reviewer"
            })

        review_context = dialogue.get_context(for_agent="Reviewer")
        review_prompt = (
            "Review the code changes described above. "
            "Check for bugs, security issues, edge cases, and correctness. "
            "If the code looks good, say 'APPROVED'. "
            "If issues exist, list them clearly so the Coder can fix them."
        )
        review_response = reviewer.think(review_prompt, context=review_context)
        dialogue.add("Reviewer", review_response, "Code Reviewer")

        # Check if approved
        if _is_approved(review_response):
            if emit:
                emit("dialogue_resolved", {
                    "topic": dialogue.topic,
                    "result": "approved",
                    "rounds": round_num + 1
                })
            break

        # Coder revises
        if round_num < max_rounds - 1:
            if emit:
                emit("dialogue_exchange", {
                    "round": round_num + 1,
                    "from": "Reviewer",
                    "to": "Coder"
                })

            revision_context = dialogue.get_context(for_agent="Coder")
            revision_prompt = (
                "The Reviewer found issues with your code. "
                "Fix all the issues mentioned above. "
                "Apply the changes using Edit or Write tools."
            )
            revision_response = coder.think(revision_prompt, context=revision_context)
            dialogue.add("Coder", revision_response, "Developer")

    if emit:
        emit("dialogue_end", {
            "topic": dialogue.topic,
            "exchanges": dialogue.exchange_count
        })

    return dialogue.last_entry.content if dialogue.last_entry else code_response


def run_test_debug_dialogue(
    tester,
    debugger,
    task: str,
    emit: Optional[Callable[[str, Any], None]] = None,
    max_rounds: int = 2
) -> str:
    """
    Run a Tester ↔ Debugger dialogue.

    Flow:
    1. Tester writes and runs tests
    2. If failures, Debugger fixes them
    3. Tester re-runs tests
    4. Repeat until passing or max rounds reached

    Returns the final test response.
    """
    dialogue = DialogueRound(
        topic=f"Test & Debug: {task[:100]}",
        max_exchanges=max_rounds * 2,
        emit=emit
    )

    if emit:
        emit("dialogue_start", {"topic": dialogue.topic, "agents": ["Tester", "Debugger"]})

    # Initial testing
    test_response = tester.think(task)
    dialogue.add("Tester", test_response, "QA Engineer")

    for round_num in range(max_rounds):
        if dialogue.at_limit:
            break

        # Check if tests passed
        if _tests_passed(test_response):
            if emit:
                emit("dialogue_resolved", {
                    "topic": dialogue.topic,
                    "result": "all_passing",
                    "rounds": round_num + 1
                })
            break

        # Debugger fixes
        if emit:
            emit("dialogue_exchange", {
                "round": round_num + 1,
                "from": "Tester",
                "to": "Debugger"
            })

        debug_context = dialogue.get_context(for_agent="Debugger")
        debug_prompt = (
            "The test results above show failures. "
            "Read the failing code, diagnose the root cause, "
            "and apply fixes using Edit tools. "
            "Explain what was wrong in simple terms before fixing."
        )
        debug_response = debugger.think(debug_prompt, context=debug_context)
        dialogue.add("Debugger", debug_response, "Debug Specialist")

        # Re-run tests
        if round_num < max_rounds - 1:
            if emit:
                emit("dialogue_exchange", {
                    "round": round_num + 1,
                    "from": "Debugger",
                    "to": "Tester"
                })

            retest_context = dialogue.get_context(for_agent="Tester")
            retest_prompt = (
                "The Debugger applied fixes above. "
                "Re-run the tests to see if the issues are resolved. "
                "Report clearly what passes and what still fails."
            )
            test_response = tester.think(retest_prompt, context=retest_context)
            dialogue.add("Tester", test_response, "QA Engineer")

    if emit:
        emit("dialogue_end", {
            "topic": dialogue.topic,
            "exchanges": dialogue.exchange_count
        })

    return dialogue.last_entry.content if dialogue.last_entry else test_response


def _is_approved(review_text: str) -> bool:
    """Check if a review response indicates approval."""
    lower = review_text.lower()
    approval_signals = ['approved', 'looks good', 'lgtm', 'no issues found', 'no issues detected']
    rejection_signals = ['issue', 'bug', 'problem', 'fix', 'error', 'vulnerability', 'concern']

    has_approval = any(s in lower for s in approval_signals)
    has_rejection = any(s in lower for s in rejection_signals)

    # If explicitly approved and no strong rejection signals
    if has_approval and not has_rejection:
        return True

    # "APPROVED" as a standalone word is strong enough to override
    if 'approved' in lower and lower.count('approved') > lower.count('not approved'):
        return True

    return False


def _tests_passed(test_text: str) -> bool:
    """Check if test output indicates all tests passed."""
    lower = test_text.lower()
    pass_signals = ['all tests pass', 'tests passed', '0 failed', 'no failures', 'all passing']
    fail_signals = ['fail', 'error', 'traceback', 'assertion']

    has_pass = any(s in lower for s in pass_signals)
    has_fail = any(s in lower for s in fail_signals)

    return has_pass and not has_fail
