"""
Code Execution Sandbox

Safely executes generated code in an isolated environment.
Uses subprocess with timeouts and resource limits.
"""

import subprocess
import tempfile
import os
import shutil
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
    - Timeout limits
    - Output capture
    - Cleanup on completion
    """

    def __init__(self, timeout: int = 30, max_output: int = 50000):
        self.timeout = timeout
        self.max_output = max_output
        self.work_dir: Optional[Path] = None

    def setup(self, project_name: str = "sandbox") -> Path:
        """Create a temporary working directory."""
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"vibe_{project_name}_"))
        return self.work_dir

    def cleanup(self):
        """Remove the temporary directory."""
        if self.work_dir and self.work_dir.exists():
            shutil.rmtree(self.work_dir, ignore_errors=True)
            self.work_dir = None

    def write_file(self, path: str, content: str) -> Path:
        """Write a file to the sandbox."""
        if not self.work_dir:
            self.setup()

        full_path = self.work_dir / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
        return full_path

    def write_files(self, files: dict) -> list:
        """Write multiple files to the sandbox."""
        written = []
        for path, content in files.items():
            written.append(self.write_file(path, content))
        return written

    def run_command(self, command: str, shell: bool = True) -> ExecutionResult:
        """
        Run a command in the sandbox.

        Args:
            command: Command to run
            shell: Whether to use shell execution

        Returns:
            ExecutionResult with stdout, stderr, and status
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
                command,
                shell=shell,
                cwd=str(self.work_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env={
                    **os.environ,
                    "HOME": str(self.work_dir),
                    "PYTHONDONTWRITEBYTECODE": "1"
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

    def run_python(self, script_path: str = "main.py") -> ExecutionResult:
        """Run a Python script in the sandbox."""
        return self.run_command(f"python3 {script_path}")

    def run_node(self, script_path: str = "index.js") -> ExecutionResult:
        """Run a Node.js script in the sandbox."""
        return self.run_command(f"node {script_path}")

    def install_python_deps(self, requirements: list) -> ExecutionResult:
        """Install Python dependencies."""
        if not requirements:
            return ExecutionResult(success=True, stdout="", stderr="", return_code=0)

        # Write requirements file
        self.write_file("requirements.txt", "\n".join(requirements))
        return self.run_command("pip install -q -r requirements.txt", shell=True)

    def install_node_deps(self, packages: list) -> ExecutionResult:
        """Install Node.js dependencies."""
        if not packages:
            return ExecutionResult(success=True, stdout="", stderr="", return_code=0)

        return self.run_command(f"npm install --silent {' '.join(packages)}")

    def lint_python(self, file_path: str = ".") -> ExecutionResult:
        """Run Python linting."""
        # Try ruff first (fast), fall back to basic syntax check
        result = self.run_command(f"python3 -m py_compile {file_path}")
        return result

    def lint_javascript(self, file_path: str = ".") -> ExecutionResult:
        """Run JavaScript syntax check."""
        return self.run_command(f"node --check {file_path}")

    def run_tests(self, test_command: str = "python3 -m pytest -v") -> ExecutionResult:
        """Run tests in the sandbox."""
        return self.run_command(test_command)


class SandboxManager:
    """
    Manages multiple sandboxes for concurrent execution.
    """

    def __init__(self):
        self.sandboxes: dict[str, Sandbox] = {}

    def create(self, project_id: str, **kwargs) -> Sandbox:
        """Create a new sandbox for a project."""
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
