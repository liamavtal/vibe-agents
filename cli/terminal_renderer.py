"""Rich terminal renderer for Vibe Agents CLI.

Renders agent events with colored output, syntax highlighting,
progress spinners, and styled panels matching the web UI colors.
"""

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich.markdown import Markdown
from rich.rule import Rule
from rich import box
import time


# Agent colors matching the web UI CSS variables
AGENT_COLORS = {
    "Router": "#79c0ff",
    "Planner": "#a371f7",
    "Coder": "#58a6ff",
    "Reviewer": "#3fb950",
    "Tester": "#d29922",
    "Debugger": "#f97583",
}

AGENT_ICONS = {
    "Router": "🌐",
    "Planner": "📋",
    "Coder": "💻",
    "Reviewer": "🔍",
    "Tester": "🔧",
    "Debugger": "🐛",
}

PHASE_ICONS = {
    "Planning": "📋",
    "Coding": "💻",
    "Reviewing": "🔍",
    "Testing": "🔧",
}


class TerminalRenderer:
    """Renders orchestrator events to a rich terminal."""

    def __init__(self, verbose: bool = False):
        self.console = Console()
        self.verbose = verbose
        self._current_agent = None
        self._streaming_text = ""
        self._live = None
        self._start_time = None

    def start(self):
        """Show startup banner."""
        self._start_time = time.time()
        self.console.print()
        self.console.print(
            Text("Vibe Agents", style="bold blue") +
            Text(" - Talk naturally. Build intelligently.", style="dim")
        )
        self.console.print()

    def finish(self, success: bool = True):
        """Show completion message."""
        self._flush_stream()
        elapsed = time.time() - self._start_time if self._start_time else 0
        self.console.print()
        if success:
            self.console.print(
                f"[bold green]Done[/] in {elapsed:.1f}s"
            )
        else:
            self.console.print(
                f"[bold red]Failed[/] after {elapsed:.1f}s"
            )

    # ==================== Event Handler ====================

    def on_event(self, event_type: str, data):
        """Handle an orchestrator event. This is the main callback."""
        handler = getattr(self, f"_handle_{event_type}", None)
        if handler:
            handler(data)
        elif self.verbose:
            self.console.print(f"[dim]Event: {event_type}: {data}[/]")

    # ==================== Event Handlers ====================

    def _handle_status(self, data):
        if self.verbose:
            self.console.print(f"  [dim]{data}[/]")

    def _handle_routing(self, data):
        msg = data.get("message", data) if isinstance(data, dict) else data
        self.console.print(f"  [dim italic]Analyzing: {msg}[/]")

    def _handle_route_decision(self, data):
        if not isinstance(data, dict):
            return
        action = data.get("action", "?")
        confidence = data.get("confidence", 0)
        reasoning = data.get("reasoning", "")

        color = "green" if confidence > 0.7 else "yellow"
        self.console.print(
            f"  [{color}]-> {action}[/] "
            f"[dim]({confidence:.0%} confidence)[/]"
        )
        if reasoning and self.verbose:
            self.console.print(f"    [dim]{reasoning}[/]")

    def _handle_phase(self, data):
        self._flush_stream()
        phase = data if isinstance(data, str) else str(data)
        icon = PHASE_ICONS.get(phase, ">")
        self.console.print()
        self.console.rule(f"[bold blue]{icon} {phase}[/]", style="blue")

    def _handle_agent_message(self, data):
        if not isinstance(data, dict):
            return

        agent = data.get("agent", "Agent")
        msg_type = data.get("type", "")
        content = data.get("content", "")

        if msg_type == "thinking":
            self._flush_stream()
            self._current_agent = agent
            color = AGENT_COLORS.get(agent, "white")
            icon = AGENT_ICONS.get(agent, "*")
            self.console.print(
                f"\n  {icon} [{color} bold]{agent}[/] [dim]is thinking...[/]"
            )

        elif msg_type == "streaming":
            self._streaming_text += content
            # Print in chunks to avoid flooding
            if "\n" in content or len(self._streaming_text) > 200:
                self._flush_stream()

        elif msg_type == "tool_use":
            self._flush_stream()
            self._render_tool_use(agent, content)

        elif msg_type == "done":
            self._flush_stream()
            self._current_agent = None

        elif msg_type == "cost":
            try:
                cost_data = content if isinstance(content, dict) else {}
                if isinstance(content, str):
                    import json
                    cost_data = json.loads(content)
                cost = cost_data.get("cost_usd", 0)
                duration = cost_data.get("duration_ms", 0)
                if cost and self.verbose:
                    self.console.print(
                        f"    [dim]${cost:.4f} | {duration/1000:.1f}s[/]"
                    )
            except (ValueError, TypeError):
                pass

        elif msg_type == "error":
            self._flush_stream()
            self.console.print(f"  [red bold]Error ({agent}):[/] {content}")

        elif msg_type == "warning":
            self._flush_stream()
            self.console.print(f"  [yellow]Warning ({agent}):[/] {content}")

    def _handle_plan_ready(self, data):
        self._flush_stream()
        if not isinstance(data, dict):
            return

        name = data.get("project_name", "Project")
        summary = data.get("summary", "")
        tasks = data.get("tasks", [])
        tech = data.get("tech_stack", {})
        lang = tech.get("language", "") if isinstance(tech, dict) else ""

        table = Table(
            title=f"Plan: {name}",
            box=box.ROUNDED,
            border_style="magenta",
            title_style="bold magenta",
            show_lines=True,
        )
        table.add_column("#", style="dim", width=3)
        table.add_column("Task", style="white")

        for i, task in enumerate(tasks, 1):
            title = task.get("title", task.get("description", "Task")) if isinstance(task, dict) else str(task)
            table.add_row(str(i), title)

        if summary:
            self.console.print(f"\n  [dim]{summary}[/]")
        if lang:
            self.console.print(f"  [dim]Tech: {lang}[/]")
        self.console.print(table)

    def _handle_file_created(self, data):
        path = data.get("path", "file") if isinstance(data, dict) else str(data)
        self.console.print(f"  [green]+[/] [bold]{path}[/]")

    def _handle_file_updated(self, data):
        path = data.get("path", "file") if isinstance(data, dict) else str(data)
        self.console.print(f"  [yellow]~[/] [bold]{path}[/]")

    def _handle_review_complete(self, data):
        self._flush_stream()
        if not isinstance(data, dict):
            return
        status = data.get("status", "complete")
        summary = data.get("summary", "")
        issues = data.get("issues", [])

        color = "green" if status == "approved" else "yellow"
        self.console.print(
            f"\n  [{color} bold]Review: {status.upper()}[/]"
        )
        if summary:
            self.console.print(f"  {summary}")

        for issue in issues:
            if isinstance(issue, dict):
                sev = issue.get("severity", "info")
                text = issue.get("issue", issue.get("description", ""))
                sev_color = {"critical": "red", "warning": "yellow"}.get(sev, "blue")
                self.console.print(f"    [{sev_color}]{sev}[/]: {text}")

    def _handle_test_complete(self, data):
        self._flush_stream()
        if not isinstance(data, dict):
            self.console.print(f"  [dim]Tests: {data}[/]")
            return
        success = data.get("success", True)
        output = data.get("output", data.get("summary", ""))
        color = "green" if success else "red"
        label = "PASSED" if success else "FAILED"
        self.console.print(f"  [{color} bold]Tests {label}[/]")
        if output and self.verbose:
            self.console.print(f"  [dim]{output[:300]}[/]")

    def _handle_execution_result(self, data):
        self._flush_stream()
        if not isinstance(data, dict):
            return
        success = data.get("success", False)
        stdout = data.get("stdout", "")
        stderr = data.get("stderr", "")

        if success:
            self.console.print("  [green bold]Execution succeeded[/]")
        else:
            self.console.print("  [red bold]Execution failed[/]")

        if stdout:
            self.console.print(Syntax(stdout[:500], "text", theme="monokai"))
        if stderr:
            self.console.print(f"  [red]{stderr[:500]}[/]")

    def _handle_build_complete(self, data):
        self._flush_stream()
        if not isinstance(data, dict):
            return

        success = data.get("success", False)
        project = data.get("project", data.get("project_name", "Project"))
        files = data.get("files", [])

        self.console.print()
        if success:
            self.console.print(
                Panel(
                    f"[bold green]Build Complete![/]\n"
                    f"Project: [bold]{project}[/]\n"
                    f"Files: {len(files)}",
                    border_style="green",
                    box=box.ROUNDED,
                )
            )
            for f in files:
                self.console.print(f"  [green]+[/] {f}")
        else:
            error = data.get("error", "Unknown error")
            self.console.print(
                Panel(
                    f"[bold red]Build Failed[/]\n{error}",
                    border_style="red",
                    box=box.ROUNDED,
                )
            )

    def _handle_project_active(self, data):
        if not isinstance(data, dict):
            return
        name = data.get("name", "Project")
        self.console.print(f"  [blue]Project:[/] [bold]{name}[/]")

    def _handle_project_resumed(self, data):
        project = data.get("project", data) if isinstance(data, dict) else data
        name = project.get("name", "Project") if isinstance(project, dict) else str(project)
        self.console.print(f"  [blue]Resumed project:[/] [bold]{name}[/]")

    def _handle_dialogue_start(self, data):
        self._flush_stream()
        topic = data.get("topic", "Discussion") if isinstance(data, dict) else str(data)
        self.console.print(f"\n  [dim]─── {topic} ───[/]")

    def _handle_dialogue_exchange(self, data):
        if isinstance(data, dict):
            fr = data.get("from", "?")
            to = data.get("to", "?")
            rd = data.get("round", "?")
            self.console.print(f"  [dim]{fr} -> {to} (round {rd})[/]")

    def _handle_dialogue_resolved(self, data):
        if isinstance(data, dict):
            topic = data.get("topic", "")
            result = data.get("result", "")
            rounds = data.get("rounds", 0)
            self.console.print(
                f"  [green]Resolved:[/] {topic} - {result} ({rounds} round{'s' if rounds != 1 else ''})"
            )

    def _handle_dialogue_end(self, data):
        pass

    def _handle_chat_response(self, data):
        self._flush_stream()
        if not isinstance(data, dict):
            self.console.print(f"\n{data}")
            return

        response = data.get("response", "")
        resp_type = data.get("type", "conversation")

        if response:
            self.console.print()
            try:
                self.console.print(Markdown(response))
            except Exception:
                self.console.print(response)

    def _handle_error(self, data):
        self._flush_stream()
        text = data if isinstance(data, str) else str(data)
        self.console.print(f"\n  [red bold]Error:[/] {text}")

    def _handle_warning(self, data):
        text = data if isinstance(data, str) else str(data)
        self.console.print(f"  [yellow]Warning:[/] {text}")

    def _handle_cleared(self, _data):
        self.console.print("  [dim]Session cleared.[/]")

    # ==================== Helpers ====================

    def _render_tool_use(self, agent, content):
        """Render a tool use card."""
        try:
            import json
            tool_data = json.loads(content) if isinstance(content, str) else content
        except (ValueError, TypeError):
            tool_data = {"tool": "Unknown"}

        if not isinstance(tool_data, dict):
            return

        tool = tool_data.get("tool", "Unknown")
        inp = tool_data.get("input", {})
        color = AGENT_COLORS.get(agent, "white")

        if tool == "Bash":
            cmd = inp.get("command", "") if isinstance(inp, dict) else ""
            self.console.print(f"    [dim]$ {cmd[:120]}[/]")
        elif tool == "Write":
            f = inp.get("file", inp.get("file_path", "")) if isinstance(inp, dict) else ""
            self.console.print(f"    [green]+[/] Creating {f}")
        elif tool == "Edit":
            f = inp.get("file", inp.get("file_path", "")) if isinstance(inp, dict) else ""
            self.console.print(f"    [yellow]~[/] Editing {f}")
        elif tool == "Read":
            f = inp.get("file", inp.get("file_path", "")) if isinstance(inp, dict) else ""
            self.console.print(f"    [dim]📖 Reading {f}[/]")
        elif tool in ("Glob", "Grep"):
            pattern = inp.get("pattern", "") if isinstance(inp, dict) else ""
            self.console.print(f"    [dim]🔍 {tool}: {pattern}[/]")
        elif self.verbose:
            self.console.print(f"    [dim]🔧 {tool}[/]")

    def _flush_stream(self):
        """Print any buffered streaming text."""
        if self._streaming_text:
            text = self._streaming_text.strip()
            if text:
                agent = self._current_agent
                color = AGENT_COLORS.get(agent, "white") if agent else "white"
                # Indent streaming output
                for line in text.split("\n"):
                    self.console.print(f"    {line}")
            self._streaming_text = ""

    # ==================== Interactive Chat ====================

    def print_user_prompt(self, message: str):
        """Print the user's message."""
        self.console.print(f"\n  [bold]You:[/] {message}")

    def print_assistant_response(self, text: str):
        """Print an assistant response."""
        self.console.print()
        try:
            self.console.print(Markdown(text))
        except Exception:
            self.console.print(text)

    def print_info(self, text: str):
        """Print an info message."""
        self.console.print(f"  [blue]{text}[/]")

    def print_error(self, text: str):
        """Print an error message."""
        self.console.print(f"  [red bold]Error:[/] {text}")
