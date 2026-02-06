"""
GitHub Integration for Vibe Agents

Uses the GitHub CLI (gh) for all operations.
Requires: gh auth login (one-time setup)

Features:
- Clone repositories
- Create branches
- Commit and push changes
- Create pull requests
- List and manage issues
"""

import subprocess
import os
import re
import json
from pathlib import Path
from typing import Optional, Callable, Any
from dataclasses import dataclass


@dataclass
class GitResult:
    """Result of a git/gh operation."""
    success: bool
    output: str
    error: Optional[str] = None


class GitHubIntegration:
    """
    GitHub integration using the gh CLI.

    All operations are performed via subprocess calls to git and gh.
    Authentication is handled by gh (run 'gh auth login' once).
    """

    def __init__(
        self,
        projects_dir: str = "./projects",
        on_event: Optional[Callable[[str, Any], None]] = None
    ):
        self.projects_dir = Path(projects_dir).resolve()
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.on_event = on_event

    def emit(self, event_type: str, data: Any):
        """Emit an event to the UI."""
        if self.on_event:
            self.on_event(event_type, data)

    def _run(self, args: list[str], cwd: Optional[str] = None) -> GitResult:
        """Run a command and return the result."""
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=cwd or str(self.projects_dir)
            )
            return GitResult(
                success=result.returncode == 0,
                output=result.stdout.strip(),
                error=result.stderr.strip() if result.returncode != 0 else None
            )
        except subprocess.TimeoutExpired:
            return GitResult(success=False, output="", error="Command timed out")
        except FileNotFoundError as e:
            return GitResult(success=False, output="", error=f"Command not found: {e}")
        except Exception as e:
            return GitResult(success=False, output="", error=str(e))

    # ==================== Auth & Status ====================

    def check_gh_auth(self) -> GitResult:
        """Check if gh CLI is authenticated."""
        return self._run(["gh", "auth", "status"])

    def check_git_installed(self) -> GitResult:
        """Check if git is installed."""
        return self._run(["git", "--version"])

    def get_status(self) -> dict:
        """Get overall GitHub integration status."""
        git_check = self.check_git_installed()
        gh_check = self.check_gh_auth()

        return {
            "git_installed": git_check.success,
            "git_version": git_check.output if git_check.success else None,
            "gh_authenticated": gh_check.success,
            "gh_user": self._extract_gh_user(gh_check.output) if gh_check.success else None,
            "ready": git_check.success and gh_check.success
        }

    def _extract_gh_user(self, output: str) -> Optional[str]:
        """Extract username from gh auth status output."""
        match = re.search(r'Logged in to github\.com account (\S+)', output)
        return match.group(1) if match else None

    # ==================== Clone ====================

    def clone(self, repo_url: str, directory: Optional[str] = None) -> GitResult:
        """
        Clone a GitHub repository.

        Args:
            repo_url: GitHub URL or owner/repo format
            directory: Optional target directory name

        Returns:
            GitResult with the cloned directory path in output
        """
        # Normalize repo URL
        if not repo_url.startswith(('http://', 'https://', 'git@')):
            # Assume owner/repo format
            repo_url = f"https://github.com/{repo_url}.git"

        # Extract repo name for directory
        if not directory:
            match = re.search(r'/([^/]+?)(?:\.git)?$', repo_url)
            directory = match.group(1) if match else "repo"

        target_path = self.projects_dir / directory

        self.emit("github", {"action": "clone", "repo": repo_url, "status": "starting"})

        if target_path.exists():
            # Already exists - do a pull instead
            self.emit("github", {"action": "clone", "status": "exists, pulling"})
            result = self._run(["git", "pull"], cwd=str(target_path))
            if result.success:
                return GitResult(success=True, output=str(target_path))
            return result

        result = self._run(["git", "clone", repo_url, str(target_path)])

        if result.success:
            self.emit("github", {"action": "clone", "status": "complete", "path": str(target_path)})
            return GitResult(success=True, output=str(target_path))

        self.emit("github", {"action": "clone", "status": "failed", "error": result.error})
        return result

    # ==================== Branch Operations ====================

    def get_current_branch(self, repo_path: str) -> GitResult:
        """Get the current branch name."""
        return self._run(["git", "branch", "--show-current"], cwd=repo_path)

    def list_branches(self, repo_path: str) -> GitResult:
        """List all branches."""
        return self._run(["git", "branch", "-a"], cwd=repo_path)

    def create_branch(self, repo_path: str, branch_name: str) -> GitResult:
        """Create and checkout a new branch."""
        self.emit("github", {"action": "branch", "name": branch_name, "status": "creating"})
        result = self._run(["git", "checkout", "-b", branch_name], cwd=repo_path)
        if result.success:
            self.emit("github", {"action": "branch", "name": branch_name, "status": "created"})
        return result

    def checkout_branch(self, repo_path: str, branch_name: str) -> GitResult:
        """Checkout an existing branch."""
        return self._run(["git", "checkout", branch_name], cwd=repo_path)

    # ==================== Commit & Push ====================

    def get_status_summary(self, repo_path: str) -> GitResult:
        """Get git status summary."""
        return self._run(["git", "status", "--short"], cwd=repo_path)

    def get_diff(self, repo_path: str, staged: bool = False) -> GitResult:
        """Get diff of changes."""
        args = ["git", "diff"]
        if staged:
            args.append("--staged")
        return self._run(args, cwd=repo_path)

    def stage_all(self, repo_path: str) -> GitResult:
        """Stage all changes."""
        return self._run(["git", "add", "-A"], cwd=repo_path)

    def commit(self, repo_path: str, message: str) -> GitResult:
        """Create a commit with the given message."""
        self.emit("github", {"action": "commit", "message": message[:50], "status": "committing"})

        # Stage all changes first
        stage_result = self.stage_all(repo_path)
        if not stage_result.success:
            return stage_result

        result = self._run(["git", "commit", "-m", message], cwd=repo_path)

        if result.success:
            self.emit("github", {"action": "commit", "status": "complete"})
        return result

    def push(self, repo_path: str, branch: Optional[str] = None, set_upstream: bool = False) -> GitResult:
        """Push commits to remote."""
        args = ["git", "push"]

        if set_upstream:
            args.extend(["-u", "origin"])
            if branch:
                args.append(branch)
        elif branch:
            args.extend(["origin", branch])

        self.emit("github", {"action": "push", "status": "pushing"})
        result = self._run(args, cwd=repo_path)

        if result.success:
            self.emit("github", {"action": "push", "status": "complete"})
        return result

    def commit_and_push(self, repo_path: str, message: str) -> GitResult:
        """Commit all changes and push."""
        commit_result = self.commit(repo_path, message)
        if not commit_result.success:
            return commit_result

        # Get current branch
        branch_result = self.get_current_branch(repo_path)
        branch = branch_result.output if branch_result.success else "main"

        return self.push(repo_path, branch, set_upstream=True)

    # ==================== Pull Requests ====================

    def create_pr(
        self,
        repo_path: str,
        title: str,
        body: str,
        base: str = "main",
        draft: bool = False
    ) -> GitResult:
        """
        Create a pull request.

        Returns the PR URL in the output.
        """
        self.emit("github", {"action": "pr", "title": title, "status": "creating"})

        args = ["gh", "pr", "create", "--title", title, "--body", body, "--base", base]
        if draft:
            args.append("--draft")

        result = self._run(args, cwd=repo_path)

        if result.success:
            self.emit("github", {"action": "pr", "status": "created", "url": result.output})
        return result

    def list_prs(self, repo_path: str, state: str = "open") -> GitResult:
        """List pull requests."""
        return self._run(
            ["gh", "pr", "list", "--state", state, "--json", "number,title,state,url"],
            cwd=repo_path
        )

    def get_pr(self, repo_path: str, pr_number: int) -> GitResult:
        """Get details of a specific PR."""
        return self._run(
            ["gh", "pr", "view", str(pr_number), "--json", "number,title,body,state,url,additions,deletions"],
            cwd=repo_path
        )

    # ==================== Issues ====================

    def list_issues(self, repo_path: str, state: str = "open") -> GitResult:
        """List issues."""
        return self._run(
            ["gh", "issue", "list", "--state", state, "--json", "number,title,state,url,labels"],
            cwd=repo_path
        )

    def get_issue(self, repo_path: str, issue_number: int) -> GitResult:
        """Get details of a specific issue."""
        return self._run(
            ["gh", "issue", "view", str(issue_number), "--json", "number,title,body,state,url,labels,comments"],
            cwd=repo_path
        )

    def create_issue(self, repo_path: str, title: str, body: str) -> GitResult:
        """Create a new issue."""
        return self._run(
            ["gh", "issue", "create", "--title", title, "--body", body],
            cwd=repo_path
        )

    # ==================== Repo Info ====================

    def get_repo_info(self, repo_path: str) -> GitResult:
        """Get repository information."""
        return self._run(
            ["gh", "repo", "view", "--json", "name,owner,description,url,defaultBranchRef"],
            cwd=repo_path
        )

    def get_remote_url(self, repo_path: str) -> GitResult:
        """Get the remote origin URL."""
        return self._run(["git", "remote", "get-url", "origin"], cwd=repo_path)
