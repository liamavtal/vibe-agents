"""WebSocket client for connecting to a running Vibe Agents server.

Sends prompts and receives events over WebSocket,
rendering them through the terminal renderer.
"""

import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    websockets = None

from .terminal_renderer import TerminalRenderer


class VibeClient:
    """WebSocket client that connects to a running Vibe Agents server."""

    def __init__(self, host: str = "localhost", port: int = 8000, verbose: bool = False):
        self.host = host
        self.port = port
        self.renderer = TerminalRenderer(verbose=verbose)
        self.session_id = None
        self._done_event = None

    async def connect_and_send(self, message: str, mode: str = "chat"):
        """Connect to server, send a message, and render events until done."""
        if websockets is None:
            self.renderer.print_error(
                "websockets package required. Install with: pip install websockets"
            )
            return False

        uri = f"ws://{self.host}:{self.port}/api/ws"
        self.renderer.start()
        self.renderer.print_info(f"Connecting to {uri}...")

        try:
            async with websockets.connect(uri) as ws:
                self._done_event = asyncio.Event()

                # Wait for session creation
                resp = await ws.recv()
                data = json.loads(resp)
                if data.get("type") == "session_created":
                    self.session_id = data.get("session_id")
                    self.renderer.print_info(f"Session: {self.session_id}")

                # Send the message
                self.renderer.print_user_prompt(message)

                if mode == "build":
                    payload = {
                        "type": "build",
                        "prompt": message,
                        "session_id": self.session_id,
                    }
                else:
                    payload = {
                        "type": "chat",
                        "message": message,
                        "session_id": self.session_id,
                    }

                await ws.send(json.dumps(payload))

                # Receive events until completion
                success = await self._receive_loop(ws)
                self.renderer.finish(success)
                return success

        except ConnectionRefusedError:
            self.renderer.print_error(
                f"Could not connect to {uri}. Is the server running?"
            )
            self.renderer.print_info("Start the server with: vibe --server")
            return False
        except Exception as e:
            self.renderer.print_error(f"Connection error: {e}")
            return False

    async def interactive(self):
        """Run an interactive chat session over WebSocket."""
        if websockets is None:
            self.renderer.print_error(
                "websockets package required. Install with: pip install websockets"
            )
            return

        uri = f"ws://{self.host}:{self.port}/api/ws"
        self.renderer.start()
        self.renderer.print_info(f"Connecting to {uri}...")
        self.renderer.print_info("Type 'exit' or 'quit' to disconnect.\n")

        try:
            async with websockets.connect(uri) as ws:
                # Wait for session creation
                resp = await ws.recv()
                data = json.loads(resp)
                if data.get("type") == "session_created":
                    self.session_id = data.get("session_id")

                while True:
                    try:
                        message = input("\n  You: ").strip()
                    except (EOFError, KeyboardInterrupt):
                        break

                    if not message or message.lower() in ("exit", "quit"):
                        break

                    payload = {
                        "type": "chat",
                        "message": message,
                        "session_id": self.session_id,
                    }
                    await ws.send(json.dumps(payload))
                    await self._receive_loop(ws)

        except ConnectionRefusedError:
            self.renderer.print_error(
                f"Could not connect to {uri}. Is the server running?"
            )
        except Exception as e:
            self.renderer.print_error(f"Connection error: {e}")

    async def _receive_loop(self, ws) -> bool:
        """Receive events from WebSocket until a terminal event."""
        success = True
        terminal_types = {
            "chat_response", "build_complete", "error",
            "project_resumed", "cleared",
        }

        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=300)
                data = json.loads(raw)
                event_type = data.get("type", "")
                event_data = data.get("data", "")

                self.renderer.on_event(event_type, event_data)

                if event_type in terminal_types:
                    if event_type == "error":
                        success = False
                    break

        except asyncio.TimeoutError:
            self.renderer.print_error("Timed out waiting for response (5 min)")
            success = False
        except websockets.exceptions.ConnectionClosed:
            self.renderer.print_error("Server disconnected")
            success = False

        return success


def run_client(message: str, mode: str = "chat",
               host: str = "localhost", port: int = 8000,
               verbose: bool = False) -> bool:
    """Convenience function to run the client."""
    client = VibeClient(host=host, port=port, verbose=verbose)
    return asyncio.run(client.connect_and_send(message, mode))


def run_interactive(host: str = "localhost", port: int = 8000,
                    verbose: bool = False):
    """Convenience function to run interactive mode."""
    client = VibeClient(host=host, port=port, verbose=verbose)
    asyncio.run(client.interactive())
