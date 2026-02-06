#!/usr/bin/env python3
"""
Vibe Agents - Startup script with network info display.

Starts the server and prints all available access URLs.
Works on Windows, macOS, and Linux.

Usage:
    python deploy/start.py
    python deploy/start.py --port 9000
    python deploy/start.py --host 127.0.0.1 --port 8080
"""

import argparse
import socket
import sys
import os

# Add project root to path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def get_local_ips() -> list[str]:
    """Get all local IPv4 addresses."""
    ips = []
    try:
        # Connect to external address to find primary interface
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(1)
            try:
                s.connect(("8.8.8.8", 80))
                primary_ip = s.getsockname()[0]
                if primary_ip and primary_ip != "0.0.0.0":
                    ips.append(primary_ip)
            except (socket.timeout, OSError):
                pass
    except Exception:
        pass

    # Also try hostname resolution
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and ip != "127.0.0.1":
                ips.append(ip)
    except Exception:
        pass

    return ips


def print_banner(host: str, port: int):
    """Print startup banner with access URLs."""
    W = 50  # inner width of the box

    def row(text):
        print(f"  |{text:<{W}}|")

    ips = get_local_ips()

    print()
    print(f"  +{'=' * W}+")
    row("        Vibe Agents - Server Starting         ")
    print(f"  +{'=' * W}+")
    row(f"  Host: {host}")
    row(f"  Port: {port}")
    print(f"  +{'=' * W}+")
    row("  Access URLs:")
    row(f"    Local:   http://localhost:{port}")
    for ip in ips:
        row(f"    Network: http://{ip}:{port}")
    print(f"  +{'=' * W}+")
    row("  Endpoints:")
    row(f"    UI:      http://localhost:{port}/")
    row(f"    API:     http://localhost:{port}/api/")
    row(f"    Health:  http://localhost:{port}/api/health")
    row(f"    Docs:    http://localhost:{port}/docs")
    print(f"  +{'=' * W}+")
    print()
    print("  Press Ctrl+C to stop the server.")
    print()


def main():
    parser = argparse.ArgumentParser(description="Start Vibe Agents server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", "-p", type=int, default=8000, help="Bind port (default: 8000)")
    args = parser.parse_args()

    print_banner(args.host, args.port)

    try:
        import uvicorn
        from backend.main import app
        uvicorn.run(app, host=args.host, port=args.port)
    except ImportError as e:
        print(f"  [ERROR] Missing dependency: {e}")
        print("  Install with: pip install -r backend/requirements.txt")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n  Server stopped.")


if __name__ == "__main__":
    main()
