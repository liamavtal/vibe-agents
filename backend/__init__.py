# Vibe Agents Backend

import os
import shutil
import platform


def find_claude_cli() -> str | None:
    """
    Find the claude CLI executable path.

    Checks:
    1. System PATH via shutil.which()
    2. Common npm global install locations

    Returns the full path to claude executable, or None if not found.
    """
    # Try standard PATH first
    claude_path = shutil.which("claude")
    if claude_path:
        return claude_path

    # Common locations to check
    home = os.path.expanduser("~")
    system = platform.system()

    candidates = []

    if system == "Windows":
        # Windows npm global paths
        appdata = os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming"))
        candidates.extend([
            os.path.join(appdata, "npm", "claude.cmd"),
            os.path.join(appdata, "npm", "claude"),
            os.path.join(home, "AppData", "Roaming", "npm", "claude.cmd"),
            os.path.join(home, "AppData", "Roaming", "npm", "claude"),
        ])
    else:
        # Unix-like (macOS, Linux)
        candidates.extend([
            os.path.join(home, ".npm-global", "bin", "claude"),
            "/usr/local/bin/claude",
            "/opt/homebrew/bin/claude",
        ])
        # Check nvm versions
        nvm_dir = os.path.join(home, ".nvm", "versions", "node")
        if os.path.isdir(nvm_dir):
            try:
                for version in os.listdir(nvm_dir):
                    candidates.append(os.path.join(nvm_dir, version, "bin", "claude"))
            except OSError:
                pass

    # Check each candidate
    for path in candidates:
        if os.path.isfile(path):
            return path

    return None


# Cache the found path
_claude_cli_path: str | None = None


def get_claude_cli() -> str:
    """
    Get the claude CLI path, raising an error if not found.
    Caches the result for performance.
    """
    global _claude_cli_path

    if _claude_cli_path is None:
        _claude_cli_path = find_claude_cli()

    if _claude_cli_path is None:
        raise FileNotFoundError(
            "Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
        )

    return _claude_cli_path
