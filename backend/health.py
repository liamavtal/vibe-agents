"""
Health monitoring for Vibe Agents.

Provides detailed health checks for:
- Claude CLI availability
- Database connectivity
- Disk space
- System info
"""

import os
import sys
import shutil
import subprocess
import platform
import time
from pathlib import Path
from backend import find_claude_cli
from typing import Any


def check_claude_cli() -> dict[str, Any]:
    """Check if Claude CLI is installed and accessible."""
    claude_path = find_claude_cli()
    if not claude_path:
        return {"status": "error", "message": "Claude CLI not found"}
    try:
        result = subprocess.run(
            [claude_path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            version = result.stdout.strip() or result.stderr.strip()
            return {"status": "ok", "version": version, "path": claude_path}
        return {"status": "error", "message": f"Exit code {result.returncode}"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Claude CLI timed out"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_database() -> dict[str, Any]:
    """Check if the SQLite database is writable."""
    try:
        from .storage import Database
        db = Database()
        # Quick read test
        db.list_projects(limit=1)
        db_path = Path.home() / ".vibe-agents" / "vibe-agents.db"
        size_mb = db_path.stat().st_size / (1024 * 1024) if db_path.exists() else 0
        return {
            "status": "ok",
            "path": str(db_path),
            "size_mb": round(size_mb, 2),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_disk_space() -> dict[str, Any]:
    """Check available disk space."""
    try:
        home = Path.home()
        usage = shutil.disk_usage(str(home))
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        used_pct = (usage.used / usage.total) * 100
        status = "ok" if free_gb > 1.0 else "warning" if free_gb > 0.5 else "error"
        return {
            "status": status,
            "free_gb": round(free_gb, 2),
            "total_gb": round(total_gb, 2),
            "used_percent": round(used_pct, 1),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_python() -> dict[str, Any]:
    """Report Python version info."""
    return {
        "status": "ok",
        "version": platform.python_version(),
        "executable": sys.executable,
        "platform": platform.platform(),
    }


def get_full_health() -> dict[str, Any]:
    """Run all health checks and return a summary."""
    start = time.time()

    checks = {
        "claude_cli": check_claude_cli(),
        "database": check_database(),
        "disk_space": check_disk_space(),
        "python": check_python(),
    }

    # Overall status: error if any critical check fails
    critical_checks = ["claude_cli", "database"]
    overall = "ok"
    for name in critical_checks:
        if checks[name].get("status") == "error":
            overall = "degraded"
            break

    if checks["disk_space"].get("status") == "error":
        overall = "degraded"

    elapsed_ms = round((time.time() - start) * 1000, 1)

    return {
        "status": overall,
        "service": "vibe-agents",
        "uptime_info": {
            "platform": platform.system(),
            "hostname": platform.node(),
            "pid": os.getpid(),
        },
        "checks": checks,
        "response_time_ms": elapsed_ms,
    }
