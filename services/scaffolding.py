import os
import shutil
import subprocess
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse, urlunparse

from services.models import WorkspaceTriggerPayload

logger = logging.getLogger("hephaestus.services.scaffolding")


class ScaffoldingError(Exception):
    """Raised when repository scaffolding or initialization fails."""
    pass


class GitRunner:
    """Helper for deterministic Git CLI operations with real-time log streaming."""

    @staticmethod
    def run_git(
        args: List[str],
        cwd: Path,
        env: Optional[Dict[str, str]] = None,
        stream_logs: bool = True
    ) -> subprocess.CompletedProcess:
        from services.events import event_bus, GIT_LOG_STREAM

        cmd = ["git"] + args
        git_env = os.environ.copy()
        if env:
            git_env.update(env)
        # Avoid hanging on interactive credential prompts
        git_env["GIT_TERMINAL_PROMPT"] = "0"

        cmd_str = " ".join(cmd)
        stdout_lines: List[str] = []
        stderr_lines: List[str] = []

        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=git_env,
                bufsize=1
            )

            # Stream stdout
            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    line_clean = line.rstrip("\n")
                    stdout_lines.append(line_clean)
                    if stream_logs:
                        event_bus.emit(GIT_LOG_STREAM, {"line": line_clean, "cmd": cmd_str, "cwd": str(cwd)})

            # Stream stderr
            if process.stderr:
                for line in iter(process.stderr.readline, ""):
                    line_clean = line.rstrip("\n")
                    stderr_lines.append(line_clean)
                    if stream_logs:
                        event_bus.emit(GIT_LOG_STREAM, {"line": line_clean, "cmd": cmd_str, "cwd": str(cwd), "is_err": True})

            process.wait()
            stdout_text = "\n".join(stdout_lines)
            stderr_text = "\n".join(stderr_lines)

            if process.returncode != 0:
                err_msg = f"Git command failed: {cmd_str}\nStderr: {stderr_text.strip()}\nStdout: {stdout_text.strip()}"
                logger.error(err_msg)
                raise ScaffoldingError(err_msg)

            return subprocess.CompletedProcess(
                args=cmd,
                returncode=process.returncode,
                stdout=stdout_text,
                stderr=stderr_text
            )
        except (OSError, FileNotFoundError) as exc:
            err_msg = f"Failed to execute git command {cmd_str}: {exc}"
            logger.error(err_msg)
            raise ScaffoldingError(err_msg)

    @staticmethod
    def get_current_commit_sha(cwd: Path) -> str:
        """Returns full SHA of HEAD commit."""
        res = GitRunner.run_git(["rev-parse", "HEAD"], cwd=cwd, stream_logs=False)
        return res.stdout.strip()

    @staticmethod
    def remote_exists(cwd: Path, remote: str = "origin") -> bool:
        """Returns True if the specified git remote exists."""
        try:
            res = GitRunner.run_git(["remote"], cwd=cwd, stream_logs=False)
            return remote in res.stdout.split()
        except ScaffoldingError:
            return False

    @staticmethod
    def set_remote_origin(cwd: Path, remote_url: str) -> None:
        """Sets or updates the 'origin' remote URL."""
        if GitRunner.remote_exists(cwd, "origin"):
            GitRunner.run_git(["remote", "set-url", "origin", remote_url], cwd=cwd)
        else:
            GitRunner.run_git(["remote", "add", "origin", remote_url], cwd=cwd)

    @staticmethod
    def push_branch(cwd: Path, branch: str, remote: str = "origin", set_upstream: bool = True) -> subprocess.CompletedProcess:
        """Pushes branch to remote."""
        args = ["push"]
        if set_upstream:
            args.append("-u")
        args.extend([remote, branch])
        return GitRunner.run_git(args, cwd=cwd)


class ScaffoldingEngine:
    """
    Deterministic workspace scaffolding engine.
    Sets up isolated directories, initializes/clones Git repos, and stages files.
    """

    def __init__(self, default_github_token: Optional[str] = None):
        self.default_github_token = default_github_token or os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_APP_TOKEN")

    def create_workspace_directory(self, workspaces_root: Path, ticket_key: str) -> Path:
        """
        Generates an isolated working directory: workspaces_root / f"{ticket_key}_{int(time.time())}".
        """
        timestamp = int(time.time())
        # Clean ticket_key for filesystem safety
        safe_key = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in ticket_key)
        working_dir = workspaces_root / f"{safe_key}_{timestamp}"
        working_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created workspace directory: {working_dir}")
        return working_dir

    def format_authenticated_url(self, repo_url: str, token: Optional[str] = None) -> str:
        """
        Injects authentication token into HTTPS GitHub/Git URLs if token is available.
        Leaves local paths or SSH URLs untouched.
        """
        auth_token = token or self.default_github_token
        if not auth_token or not repo_url.startswith("http"):
            return repo_url

        parsed = urlparse(repo_url)
        # Avoid injecting token if already present in netloc
        if "@" in parsed.netloc:
            return repo_url

        netloc = f"x-access-token:{auth_token}@{parsed.netloc}"
        return urlunparse(parsed._replace(netloc=netloc))

    def unpack_starter_template(self, working_dir: Path, ticket_key: str) -> List[str]:
        """
        Unpacks a standard base starter template:
        - baseline .gitignore
        - boilerplate README.md
        - basic LICENSE (MIT)
        """
        created_files = []

        # 1. .gitignore
        gitignore_path = working_dir / ".gitignore"
        if not gitignore_path.exists():
            gitignore_content = """# Environments & Bytecode
__pycache__/
*.py[cod]
*$py.class
.venv/
env/
venv/
node_modules/
dist/
build/

# IDEs & OS
.DS_Store
.idea/
.vscode/
*.swp

# Secrets & Environment variables
.env
*.local.env

# Agent harness scratch files
.harness_inbox/
*.tmp
"""
            gitignore_path.write_text(gitignore_content, encoding="utf-8")
            created_files.append(".gitignore")

        # 2. README.md
        readme_path = working_dir / "README.md"
        if not readme_path.exists():
            readme_content = f"""# Project {ticket_key}

Autonomously scaffolded project workspace for Jira task `{ticket_key}`.

## Overview
This repository contains the codebase managed by the Hephaestus autonomous agent harness.

## Getting Started
Refer to the task instructions and platform configuration for execution hooks and automated tests.
"""
            readme_path.write_text(readme_content, encoding="utf-8")
            created_files.append("README.md")

        # 3. LICENSE (MIT)
        license_path = working_dir / "LICENSE"
        if not license_path.exists():
            year = time.strftime("%Y")
            license_content = f"""MIT License

Copyright (c) {year} Hephaestus Autonomous Workspace

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
            license_path.write_text(license_content, encoding="utf-8")
            created_files.append("LICENSE")

        return created_files

    def inject_platform_baseline(self, working_dir: Path, target_platform: str) -> List[str]:
        """
        Injects target platform baseline configuration files:
        - GOOGLE_JULES: .jules/config.yaml stub
        - CODEX_CLOUD: .codex/instructions.md entry point stub
        - LOCAL_CONTAINER: Dockerfile stub, docker-compose.yml, .env.example
        """
        created = []
        if target_platform == "GOOGLE_JULES":
            jules_dir = working_dir / ".jules"
            jules_dir.mkdir(parents=True, exist_ok=True)
            cfg_path = jules_dir / "config.yaml"
            if not cfg_path.exists():
                cfg_path.write_text(
                    """version: 1
platform: google_jules
execution:
  enforce_clean_git: true
  auto_test: true
hooks:
  build: null
  test: pytest
""",
                    encoding="utf-8"
                )
                created.append(".jules/config.yaml")

        elif target_platform == "CODEX_CLOUD":
            codex_dir = working_dir / ".codex"
            codex_dir.mkdir(parents=True, exist_ok=True)
            instructions_path = codex_dir / "instructions.md"
            if not instructions_path.exists():
                instructions_path.write_text(
                    """# OpenAI Codex Cloud Configuration
- Ensure top-level execution entrypoints are registered.
- Maintain idempotent build configurations.
""",
                    encoding="utf-8"
                )
                created.append(".codex/instructions.md")

        elif target_platform == "LOCAL_CONTAINER":
            dockerfile = working_dir / "Dockerfile"
            if not dockerfile.exists():
                dockerfile.write_text(
                    """FROM python:3.12-slim
WORKDIR /workspace
COPY . /workspace
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi
CMD ["bash"]
""",
                    encoding="utf-8"
                )
                created.append("Dockerfile")

            compose_file = working_dir / "docker-compose.yml"
            if not compose_file.exists():
                compose_file.write_text(
                    """version: '3.8'
services:
  app:
    build: .
    volumes:
      - .:/workspace
    environment:
      - PYTHONUNBUFFERED=1
""",
                    encoding="utf-8"
                )
                created.append("docker-compose.yml")

            env_example = working_dir / ".env.example"
            if not env_example.exists():
                env_example.write_text(
                    """# Baseline Environment Variables
DEBUG=True
PORT=8000
""",
                    encoding="utf-8"
                )
                created.append(".env.example")

        elif target_platform == "GROK_BUILD":
            grok_dir = working_dir / ".grok"
            grok_dir.mkdir(parents=True, exist_ok=True)
            cfg_path = grok_dir / "build-config.json"
            if not cfg_path.exists():
                cfg_path.write_text('{\n  "version": "1.0",\n  "platform": "GROK_BUILD"\n}\n', encoding="utf-8")
                created.append(".grok/build-config.json")

        elif target_platform == "DEVIN_AI":
            devin_path = working_dir / "devin_instructions.md"
            if not devin_path.exists():
                devin_path.write_text("# Devin AI Task Directive\n- Follow multi-step plan.\n", encoding="utf-8")
                created.append("devin_instructions.md")

        elif target_platform == "CURSOR_DEVCONTAINER":
            devcontainer_dir = working_dir / ".devcontainer"
            devcontainer_dir.mkdir(parents=True, exist_ok=True)
            dc_json = devcontainer_dir / "devcontainer.json"
            if not dc_json.exists():
                dc_json.write_text('{\n  "name": "Cursor Devcontainer",\n  "customizations": {\n    "cursor": {}\n  }\n}\n', encoding="utf-8")
                created.append(".devcontainer/devcontainer.json")

        return created

    def copy_staged_assets(self, source_staged_dir: Path, target_dir: Path) -> List[str]:
        """
        Copies all files and directories recursively from source_staged_dir into target_dir.
        Returns list of relative paths copied.
        """
        copied = []
        if not source_staged_dir.exists():
            logger.warning(f"Staged assets directory {source_staged_dir} does not exist. Skipping copy.")
            return copied

        target_dir.mkdir(parents=True, exist_ok=True)

        for item in source_staged_dir.iterdir():
            target_item = target_dir / item.name
            if item.is_dir():
                shutil.copytree(item, target_item, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target_item)
            copied.append(item.name)

        logger.info(f"Copied {len(copied)} staged assets to {target_dir}")
        return copied

    def setup_workspace(self, payload: WorkspaceTriggerPayload) -> Dict[str, Any]:
        """
        Executes isolated workspace setup depending on payload.mode:
        - PROMPT_NEW: git init -b main, starter template, platform stubs, staged files copied to root.
        - PROMPT: authenticated clone, checkout tracking branch jira-{ticket_key}-agent,
          staged files copied to .harness_inbox/.
        """
        working_dir = self.create_workspace_directory(payload.workspaces_root, payload.ticket_key)
        staged_files_dir = payload.staging_dir / "staged_files"
        # Support fallback to staging_dir / "files" if staged_files does not exist
        if not staged_files_dir.exists() and (payload.staging_dir / "files").exists():
            staged_files_dir = payload.staging_dir / "files"

        branch_name = payload.custom_branch_name or f"jira-{payload.ticket_key}-agent"

        if payload.mode == "PROMPT_NEW":
            # 1. git init -b main
            try:
                GitRunner.run_git(["init", "-b", "main"], cwd=working_dir)
            except ScaffoldingError:
                # Fallback for older git versions where -b is unsupported
                GitRunner.run_git(["init"], cwd=working_dir)
                GitRunner.run_git(["checkout", "-b", "main"], cwd=working_dir)

            branch_name = "main"

            # 2. Unpack starter template
            self.unpack_starter_template(working_dir, payload.ticket_key)

            # 3. Inject target platform baseline files
            self.inject_platform_baseline(working_dir, payload.target_platform)

            # 4. Copy all assets from staged_files directly into workspace root
            copied_files = self.copy_staged_assets(staged_files_dir, working_dir)

            # 5. Configure local user for commit and initial commit
            GitRunner.run_git(["config", "user.name", "Hephaestus Agent"], cwd=working_dir)
            GitRunner.run_git(["config", "user.email", "agent@hephaestus.internal"], cwd=working_dir)
            GitRunner.run_git(["add", "."], cwd=working_dir)
            GitRunner.run_git(
                ["commit", "-m", f"Initial scaffolding commit for {payload.ticket_key}"],
                cwd=working_dir
            )

            return {
                "working_directory": working_dir,
                "branch_name": branch_name,
                "mode": payload.mode,
                "copied_assets": copied_files,
                "inbox_directory": None
            }

        elif payload.mode == "PROMPT":
            if payload.skip_clone:
                # Selective / Agent-Aware skip clone:
                # For cloud agents (Google Jules, Codex Cloud, Devin) or when clone: false is specified in <|flags|>.
                logger.info(
                    f"Skipping git clone for {payload.ticket_key} (skip_clone=True, platform={payload.target_platform})"
                )
                try:
                    GitRunner.run_git(["init", "-b", branch_name], cwd=working_dir)
                except ScaffoldingError:
                    GitRunner.run_git(["init"], cwd=working_dir)
                    try:
                        GitRunner.run_git(["checkout", "-b", branch_name], cwd=working_dir)
                    except ScaffoldingError:
                        pass

                GitRunner.run_git(["config", "user.name", "Hephaestus Agent"], cwd=working_dir)
                GitRunner.run_git(["config", "user.email", "agent@hephaestus.internal"], cwd=working_dir)

                # Inject target platform baseline
                self.inject_platform_baseline(working_dir, payload.target_platform)

                # Copy assets into dedicated .harness_inbox/ directory
                inbox_dir = working_dir / ".harness_inbox"
                copied_files = self.copy_staged_assets(staged_files_dir, inbox_dir)

                # Commit initial scaffolding so HEAD branch is created
                GitRunner.run_git(["add", "."], cwd=working_dir)
                try:
                    GitRunner.run_git(
                        ["commit", "-m", f"Initialize workspace for {payload.ticket_key} (skip_clone=True)"],
                        cwd=working_dir
                    )
                except ScaffoldingError:
                    GitRunner.run_git(
                        ["commit", "--allow-empty", "-m", f"Initialize workspace for {payload.ticket_key} (skip_clone=True)"],
                        cwd=working_dir
                    )

                return {
                    "working_directory": working_dir,
                    "branch_name": branch_name,
                    "mode": payload.mode,
                    "cloned": False,
                    "copied_assets": copied_files,
                    "inbox_directory": inbox_dir
                }

            if not payload.repo_url:
                raise ScaffoldingError(f"repo_url must be provided for PROMPT mode (ticket {payload.ticket_key})")

            auth_repo_url = self.format_authenticated_url(payload.repo_url, payload.github_token)

            # 1. Clone repo into workspace working directory
            # For git clone into an existing directory, clone to '.'
            GitRunner.run_git(["clone", auth_repo_url, "."], cwd=working_dir)

            # Configure git user
            GitRunner.run_git(["config", "user.name", "Hephaestus Agent"], cwd=working_dir)
            GitRunner.run_git(["config", "user.email", "agent@hephaestus.internal"], cwd=working_dir)

            # 2. Create and checkout isolated tracking branch
            try:
                GitRunner.run_git(["checkout", "-b", branch_name], cwd=working_dir)
            except ScaffoldingError:
                GitRunner.run_git(["checkout", branch_name], cwd=working_dir)

            # 3. Copy assets into dedicated .harness_inbox/ directory
            inbox_dir = working_dir / ".harness_inbox"
            copied_files = self.copy_staged_assets(staged_files_dir, inbox_dir)

            return {
                "working_directory": working_dir,
                "branch_name": branch_name,
                "mode": payload.mode,
                "cloned": True,
                "copied_assets": copied_files,
                "inbox_directory": inbox_dir
            }
        else:
            raise ScaffoldingError(f"Unsupported mode: {payload.mode}")


scaffolding_engine = ScaffoldingEngine()
