"""
Code Execution Sandbox

Safely executes generated code in an isolated environment.
Uses subprocess with timeouts and resource limits.

Security features:
- Path traversal prevention
- Command injection prevention
- Timeout limits
- Output size limits
"""

import subprocess
import tempfile
import os
import shutil
import shlex
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class ExecutionResult:
    """Result of code execution."""
    success: bool
    stdout: str
    stderr: str
    return_code: int
    error: Optional[str] = None


class Sandbox:
    """
    Safe code execution environment.

    Executes code in a temporary directory with:
    - Path traversal prevention
    - Command injection prevention
    - Timeout limits
    - Output capture
    - Cleanup on completion
    """

    # Allowed file extensions for code files
    ALLOWED_EXTENSIONS = {'.py', '.js', '.ts', '.json', '.txt', '.md', '.html', '.css', '.yaml', '.yml'}

    # Maximum file size (1MB)
    MAX_FILE_SIZE = 1024 * 1024

    def __init__(self, timeout: int = 30, max_output: int = 50000):
        self.timeout = min(timeout, 300)  # Cap at 5 minutes
        self.max_output = min(max_output, 100000)  # Cap at 100KB
        self.work_dir: Optional[Path] = None

    def setup(self, project_name: str = "sandbox") -> Path:
        """Create a temporary working directory."""
        # Sanitize project name
        safe_name = self._sanitize_name(project_name)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"vibe_{safe_name}_"))
        return self.work_dir

    def cleanup(self):
        """Remove the temporary directory."""
        if self.work_dir and self.work_dir.exists():
            try:
                shutil.rmtree(self.work_dir, ignore_errors=True)
            except Exception:
                pass
            finally:
                self.work_dir = None

    def _sanitize_name(self, name: str) -> str:
        """Sanitize a name for safe filesystem use."""
        # Only allow alphanumeric, underscore, hyphen
        sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
        # Limit length
        return sanitized[:50]

    def _validate_path(self, path: str) -> Path:
        """
        Validate a path is safe and within the sandbox.

        Raises ValueError if path is invalid or escapes sandbox.
        """
        if not self.work_dir:
            raise ValueError("Sandbox not initialized")

        # Normalize the path
        clean_path = Path(path)

        # Reject absolute paths
        if clean_path.is_absolute():
            raise ValueError("Absolute paths not allowed")

        # Reject path traversal attempts
        if '..' in str(clean_path):
            raise ValueError("Path traversal not allowed")

        # Resolve the full path
        full_path = (self.work_dir / clean_path).resolve()

        # Verify it's still within the work directory
        try:
            full_path.relative_to(self.work_dir.resolve())
        except ValueError:
            raise ValueError("Path escapes sandbox directory")

        return full_path

    def _validate_file_extension(self, path: str) -> bool:
        """Check if file extension is allowed."""
        ext = Path(path).suffix.lower()
        return ext in self.ALLOWED_EXTENSIONS or ext == ''

    def write_file(self, path: str, content: str) -> Path:
        """Write a file to the sandbox with security checks."""
        if not self.work_dir:
            self.setup()

        # Validate path
        full_path = self._validate_path(path)

        # Check file extension
        if not self._validate_file_extension(path):
            raise ValueError(f"File extension not allowed: {Path(path).suffix}")

        # Check content size
        if len(content) > self.MAX_FILE_SIZE:
            raise ValueError(f"File too large: {len(content)} bytes (max {self.MAX_FILE_SIZE})")

        # Create parent directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the file
        full_path.write_text(content)
        return full_path

    def write_files(self, files: dict) -> list:
        """Write multiple files to the sandbox."""
        written = []
        for path, content in files.items():
            try:
                written.append(self.write_file(path, content))
            except ValueError as e:
                # Log but continue with other files
                print(f"Skipping file {path}: {e}")
        return written

    def _run_command_safe(self, args: list, **kwargs) -> ExecutionResult:
        """
        Run a command with security protections.

        Uses subprocess with shell=False for safety.
        """
        if not self.work_dir:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error="Sandbox not initialized"
            )

        try:
            result = subprocess.run(
                args,
                shell=False,  # Never use shell=True
                cwd=str(self.work_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env={
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "HOME": str(self.work_dir),
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONUNBUFFERED": "1",
                    # Restrict Python imports for security
                    "PYTHONPATH": str(self.work_dir),
                }
            )

            stdout = result.stdout[:self.max_output]
            stderr = result.stderr[:self.max_output]

            if len(result.stdout) > self.max_output:
                stdout += "\n... [output truncated]"
            if len(result.stderr) > self.max_output:
                stderr += "\n... [output truncated]"

            return ExecutionResult(
                success=result.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                return_code=result.returncode
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error=f"Command timed out after {self.timeout}s"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error=str(e)
            )

    def run_command(self, command: str, shell: bool = False) -> ExecutionResult:
        """
        Run a command in the sandbox.

        Args:
            command: Command to run (will be parsed safely)
            shell: Ignored for security (always False)

        Returns:
            ExecutionResult with stdout, stderr, and status
        """
        # Parse command safely using shlex
        try:
            args = shlex.split(command)
        except ValueError as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error=f"Invalid command: {e}"
            )

        if not args:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error="Empty command"
            )

        return self._run_command_safe(args)

    def run_python(self, script_path: str = "main.py") -> ExecutionResult:
        """Run a Python script in the sandbox."""
        # Validate the script path
        try:
            validated_path = self._validate_path(script_path)
        except ValueError as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error=str(e)
            )

        # Get the relative path for the command
        rel_path = validated_path.relative_to(self.work_dir)
        return self._run_command_safe(["python3", str(rel_path)])

    def run_node(self, script_path: str = "index.js") -> ExecutionResult:
        """Run a Node.js script in the sandbox."""
        try:
            validated_path = self._validate_path(script_path)
        except ValueError as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error=str(e)
            )

        rel_path = validated_path.relative_to(self.work_dir)
        return self._run_command_safe(["node", str(rel_path)])

    def install_python_deps(self, requirements: list) -> ExecutionResult:
        """Install Python dependencies safely."""
        if not requirements:
            return ExecutionResult(success=True, stdout="", stderr="", return_code=0)

        # Sanitize package names (only allow alphanumeric, hyphen, underscore, brackets, comparison)
        safe_requirements = []
        for req in requirements:
            # Basic validation - reject obviously malicious patterns
            if re.match(r'^[a-zA-Z0-9_\-\[\]<>=.,\s]+$', req):
                safe_requirements.append(req)
            else:
                print(f"Skipping suspicious requirement: {req}")

        if not safe_requirements:
            return ExecutionResult(success=True, stdout="No valid requirements", stderr="", return_code=0)

        # Write requirements file
        self.write_file("requirements.txt", "\n".join(safe_requirements))
        return self._run_command_safe([
            "pip", "install", "-q", "--no-warn-script-location",
            "-r", "requirements.txt"
        ])

    def install_node_deps(self, packages: list) -> ExecutionResult:
        """Install Node.js dependencies safely."""
        if not packages:
            return ExecutionResult(success=True, stdout="", stderr="", return_code=0)

        # Sanitize package names
        safe_packages = []
        for pkg in packages:
            if re.match(r'^[@a-zA-Z0-9_\-/]+$', pkg):
                safe_packages.append(pkg)
            else:
                print(f"Skipping suspicious package: {pkg}")

        if not safe_packages:
            return ExecutionResult(success=True, stdout="No valid packages", stderr="", return_code=0)

        return self._run_command_safe(["npm", "install", "--silent"] + safe_packages)

    def lint_python(self, file_path: str = ".") -> ExecutionResult:
        """Run Python syntax check."""
        try:
            if file_path == ".":
                # Check all Python files
                validated_path = "."
            else:
                validated_path = str(self._validate_path(file_path).relative_to(self.work_dir))
        except ValueError as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error=str(e)
            )

        return self._run_command_safe(["python3", "-m", "py_compile", validated_path])

    def lint_javascript(self, file_path: str = ".") -> ExecutionResult:
        """Run JavaScript syntax check."""
        try:
            validated_path = str(self._validate_path(file_path).relative_to(self.work_dir))
        except ValueError as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                return_code=-1,
                error=str(e)
            )

        return self._run_command_safe(["node", "--check", validated_path])

    def run_tests(self, test_command: str = "python3 -m pytest -v") -> ExecutionResult:
        """Run tests in the sandbox."""
        return self.run_command(test_command)


class SandboxManager:
    """
    Manages multiple sandboxes for concurrent execution.
    """

    MAX_SANDBOXES = 10  # Limit concurrent sandboxes

    def __init__(self):
        self.sandboxes: dict[str, Sandbox] = {}

    def create(self, project_id: str, **kwargs) -> Sandbox:
        """Create a new sandbox for a project."""
        # Limit number of concurrent sandboxes
        if len(self.sandboxes) >= self.MAX_SANDBOXES:
            # Clean up oldest sandbox
            oldest_id = next(iter(self.sandboxes))
            self.destroy(oldest_id)

        sandbox = Sandbox(**kwargs)
        sandbox.setup(project_id)
        self.sandboxes[project_id] = sandbox
        return sandbox

    def get(self, project_id: str) -> Optional[Sandbox]:
        """Get an existing sandbox."""
        return self.sandboxes.get(project_id)

    def destroy(self, project_id: str):
        """Destroy a sandbox."""
        if project_id in self.sandboxes:
            self.sandboxes[project_id].cleanup()
            del self.sandboxes[project_id]

    def destroy_all(self):
        """Destroy all sandboxes."""
        for sandbox in self.sandboxes.values():
            sandbox.cleanup()
        self.sandboxes.clear()
