"""Vibe Agents CLI - Talk naturally. Build intelligently.

Usage:
    vibe "build me a todo app"           # Smart routing (auto-detects intent)
    vibe --build "make a calculator"     # Force full pipeline mode
    vibe --code "write a fibonacci fn"   # Code-only mode
    vibe --fix "fix the bug in main.py"  # Fix mode
    vibe --review                        # Review current project
    vibe --interactive                   # Interactive chat session
    vibe --connect "prompt"              # Connect to running server
    vibe --server                        # Start the web server
    vibe --projects                      # List saved projects
    vibe --resume 3                      # Resume project by ID
"""

import argparse
import sys
import os

# Add the project root to path so imports work
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vibe",
        description="Vibe Agents - AI coding assistant. Talk naturally. Build intelligently.",
        epilog="Examples:\n"
               "  vibe \"build me a todo app\"\n"
               "  vibe --build \"create a REST API\"\n"
               "  vibe --interactive\n"
               "  vibe --server\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help="Natural language prompt (smart routing decides the action)",
    )

    # Mode flags
    mode_group = parser.add_argument_group("Modes")
    mode_group.add_argument(
        "--build", "-b",
        metavar="PROMPT",
        help="Run full pipeline (plan → code → review → test)",
    )
    mode_group.add_argument(
        "--code", "-c",
        metavar="PROMPT",
        help="Code-only mode (skip review and testing)",
    )
    mode_group.add_argument(
        "--fix", "-f",
        metavar="PROMPT",
        help="Fix/debug mode",
    )
    mode_group.add_argument(
        "--review", "-r",
        action="store_true",
        help="Review current project code",
    )
    mode_group.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Interactive chat session (standalone)",
    )

    # Server / client
    server_group = parser.add_argument_group("Server")
    server_group.add_argument(
        "--server", "-s",
        action="store_true",
        help="Start the web server (default: 0.0.0.0:8000)",
    )
    server_group.add_argument(
        "--connect",
        metavar="PROMPT",
        help="Send prompt to running server via WebSocket",
    )
    server_group.add_argument(
        "--host",
        default="0.0.0.0",
        help="Server host (default: 0.0.0.0)",
    )
    server_group.add_argument(
        "--port", "-p",
        type=int,
        default=8000,
        help="Server port (default: 8000)",
    )

    # Project management
    project_group = parser.add_argument_group("Projects")
    project_group.add_argument(
        "--projects",
        action="store_true",
        help="List saved projects",
    )
    project_group.add_argument(
        "--resume",
        type=int,
        metavar="ID",
        help="Resume a project by ID",
    )

    # Options
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output (costs, debug info)",
    )
    parser.add_argument(
        "--project-dir",
        default="./projects",
        help="Project directory (default: ./projects)",
    )

    return parser


def run_server(host: str, port: int):
    """Start the FastAPI web server."""
    try:
        import uvicorn
        from backend.main import app
        print(f"\n  Vibe Agents server starting on http://{host}:{port}")
        print(f"  Open in browser: http://localhost:{port}\n")
        uvicorn.run(app, host=host, port=port)
    except ImportError as e:
        print(f"Error: Missing dependency - {e}")
        print("Install with: pip install -r backend/requirements.txt")
        sys.exit(1)


def run_standalone(prompt: str, mode: str = "chat",
                   verbose: bool = False, project_dir: str = "./projects"):
    """Run agents directly without a server."""
    from cli.terminal_renderer import TerminalRenderer

    renderer = TerminalRenderer(verbose=verbose)
    renderer.start()

    try:
        from backend.orchestrator import Orchestrator, ConversationalOrchestrator
        from backend.storage import Database
    except ImportError as e:
        renderer.print_error(f"Missing dependency: {e}")
        renderer.print_info("Install with: pip install -r backend/requirements.txt")
        return False

    db = Database()

    def on_event(event_type, data):
        renderer.on_event(event_type, data)

    if mode == "build":
        renderer.print_user_prompt(prompt)
        orchestrator = Orchestrator(
            projects_dir=project_dir,
            on_event=on_event,
        )
        result = orchestrator.build(prompt)
        success = result.get("success", False)
        renderer.finish(success)
        return success

    else:
        renderer.print_user_prompt(prompt)
        orchestrator = ConversationalOrchestrator(
            projects_dir=project_dir,
            on_event=on_event,
            db=db,
        )
        result = orchestrator.chat(prompt)
        success = result.get("success", True) if isinstance(result, dict) else True
        renderer.finish(success)
        return success


def run_interactive_standalone(verbose: bool = False, project_dir: str = "./projects"):
    """Run an interactive chat session directly (no server)."""
    from cli.terminal_renderer import TerminalRenderer

    renderer = TerminalRenderer(verbose=verbose)
    renderer.start()
    renderer.print_info("Interactive mode. Type 'exit' or 'quit' to stop.\n")

    try:
        from backend.orchestrator import ConversationalOrchestrator
        from backend.storage import Database
    except ImportError as e:
        renderer.print_error(f"Missing dependency: {e}")
        return

    db = Database()

    def on_event(event_type, data):
        renderer.on_event(event_type, data)

    orchestrator = ConversationalOrchestrator(
        projects_dir=project_dir,
        on_event=on_event,
        db=db,
    )

    while True:
        try:
            message = input("\n  You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not message or message.lower() in ("exit", "quit", "q"):
            break

        renderer.print_user_prompt(message)
        result = orchestrator.chat(message)

        # The response is already rendered via on_event callbacks,
        # but handle the final chat_response if needed
        if isinstance(result, dict) and result.get("type") == "conversation":
            response = result.get("response", "")
            if response:
                renderer.print_assistant_response(response)

    renderer.console.print("\n  [dim]Goodbye![/]\n")


def list_projects(verbose: bool = False):
    """List all saved projects."""
    from cli.terminal_renderer import TerminalRenderer

    renderer = TerminalRenderer(verbose=verbose)

    try:
        from backend.storage import Database
    except ImportError as e:
        renderer.print_error(f"Missing dependency: {e}")
        return

    db = Database()
    projects = db.list_projects(status="active", limit=50)

    if not projects:
        renderer.console.print("\n  [dim]No projects found.[/]\n")
        return

    from rich.table import Table
    from rich import box

    table = Table(
        title="Saved Projects",
        box=box.ROUNDED,
        border_style="blue",
        title_style="bold blue",
    )
    table.add_column("ID", style="dim", width=5)
    table.add_column("Name", style="bold")
    table.add_column("Description", style="dim", max_width=40)
    table.add_column("Files", justify="right")
    table.add_column("Status", style="green")

    for p in projects:
        d = p.to_dict() if hasattr(p, "to_dict") else p
        table.add_row(
            str(d.get("id", "?")),
            d.get("name", "Untitled"),
            (d.get("description", "") or "")[:40],
            str(d.get("file_count", 0)),
            d.get("status", "active"),
        )

    renderer.console.print()
    renderer.console.print(table)
    renderer.console.print()
    renderer.console.print("  [dim]Resume with:[/] vibe --resume <ID>")
    renderer.console.print()


def resume_project(project_id: int, verbose: bool = False, project_dir: str = "./projects"):
    """Resume a saved project."""
    from cli.terminal_renderer import TerminalRenderer

    renderer = TerminalRenderer(verbose=verbose)
    renderer.start()

    try:
        from backend.orchestrator import ConversationalOrchestrator
        from backend.storage import Database
    except ImportError as e:
        renderer.print_error(f"Missing dependency: {e}")
        return

    db = Database()

    def on_event(event_type, data):
        renderer.on_event(event_type, data)

    orchestrator = ConversationalOrchestrator(
        projects_dir=project_dir,
        on_event=on_event,
        db=db,
    )

    result = orchestrator.resume_project(project_id)

    if result.get("error"):
        renderer.print_error(result["error"])
        renderer.finish(False)
        return

    renderer.print_info("Project resumed. Entering interactive mode.")
    renderer.print_info("Type 'exit' or 'quit' to stop.\n")

    while True:
        try:
            message = input("\n  You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not message or message.lower() in ("exit", "quit", "q"):
            break

        renderer.print_user_prompt(message)
        result = orchestrator.chat(message)

        if isinstance(result, dict) and result.get("type") == "conversation":
            response = result.get("response", "")
            if response:
                renderer.print_assistant_response(response)

    renderer.console.print("\n  [dim]Goodbye![/]\n")


def main():
    parser = create_parser()
    args = parser.parse_args()

    # Server mode
    if args.server:
        run_server(args.host, args.port)
        return

    # Client mode (connect to server)
    if args.connect:
        from cli.client import run_client
        success = run_client(
            args.connect,
            mode="chat",
            host=args.host if args.host != "0.0.0.0" else "localhost",
            port=args.port,
            verbose=args.verbose,
        )
        sys.exit(0 if success else 1)

    # List projects
    if args.projects:
        list_projects(verbose=args.verbose)
        return

    # Resume project
    if args.resume:
        resume_project(
            args.resume,
            verbose=args.verbose,
            project_dir=args.project_dir,
        )
        return

    # Interactive standalone
    if args.interactive:
        run_interactive_standalone(
            verbose=args.verbose,
            project_dir=args.project_dir,
        )
        return

    # Full pipeline build
    if args.build:
        success = run_standalone(
            args.build,
            mode="build",
            verbose=args.verbose,
            project_dir=args.project_dir,
        )
        sys.exit(0 if success else 1)

    # Code-only / fix / review
    if args.code:
        success = run_standalone(
            args.code,
            mode="chat",
            verbose=args.verbose,
            project_dir=args.project_dir,
        )
        sys.exit(0 if success else 1)

    if args.fix:
        success = run_standalone(
            args.fix,
            mode="chat",
            verbose=args.verbose,
            project_dir=args.project_dir,
        )
        sys.exit(0 if success else 1)

    if args.review:
        success = run_standalone(
            "Review the current project code for issues and improvements",
            mode="chat",
            verbose=args.verbose,
            project_dir=args.project_dir,
        )
        sys.exit(0 if success else 1)

    # Default: smart routing with positional prompt
    if args.prompt:
        success = run_standalone(
            args.prompt,
            mode="chat",
            verbose=args.verbose,
            project_dir=args.project_dir,
        )
        sys.exit(0 if success else 1)

    # No arguments - show help
    parser.print_help()


if __name__ == "__main__":
    main()
