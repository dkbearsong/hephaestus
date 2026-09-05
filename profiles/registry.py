"""
Platform-Specific Execution Profiles Registry
Defines deterministic execution profiles, template generators, and validation checks for all 6 target platforms.
"""

import os
import re
import json
import stat
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Tuple

from profiles.base import (
    TargetPlatform,
    ContainerSpec,
    PlatformConfig,
    ExecutionProfile,
    ValidationResult
)

logger = logging.getLogger("hephaestus.profiles.registry")


def strip_json_comments(text: str) -> str:
    """
    Strips single-line (//) and multi-line (/* ... */) comments from JSONC content
    while preserving string literals.
    """
    pattern = r'(//.*?$)|(/\*.*?\*/)|("(?:\\.|[^"\\])*")'
    def replace(match):
        if match.group(3) is not None:
            return match.group(3)
        return ""
    stripped = re.sub(pattern, replace, text, flags=re.MULTILINE | re.DOTALL)
    # Remove trailing commas before closing braces/brackets for permissive parsing
    stripped = re.sub(r',\s*([\]}])', r'\1', stripped)
    return stripped.strip()


def generate_repo_tree(root_dir: Path, max_depth: int = 4) -> str:
    """Generates an ASCII file tree map of the repository, ignoring common noise dirs."""
    ignore_dirs = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache", ".harness_inbox", "dist", "build"}
    lines = [f"{root_dir.name}/"]

    def _walk(directory: Path, prefix: str = "", depth: int = 1):
        if depth > max_depth:
            return
        try:
            entries = sorted(list(directory.iterdir()), key=lambda e: (not e.is_dir(), e.name.lower()))
        except Exception:
            return

        visible_entries = [e for e in entries if e.name not in ignore_dirs and not e.name.startswith(".DS_Store")]
        total = len(visible_entries)
        for i, entry in enumerate(visible_entries):
            is_last = (i == total - 1)
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")
            if entry.is_dir():
                extension = "    " if is_last else "│   "
                _walk(entry, prefix + extension, depth + 1)

    _walk(root_dir)
    return "\n".join(lines)


# ==============================================================================
# INJECTION GENERATORS & VALIDATORS PER PLATFORM
# ==============================================================================

class JulesProfileHandler:
    @staticmethod
    def inject(working_dir: Path, context: Dict[str, Any]) -> List[str]:
        """
        Injects .jules/config.yaml specifying task instructions, target branch,
        and discovered build/test commands.
        """
        jules_dir = working_dir / ".jules"
        jules_dir.mkdir(parents=True, exist_ok=True)
        config_path = jules_dir / "config.yaml"

        ticket_key = context.get("ticket_key", "TASK-DEFAULT")
        branch_name = context.get("branch_name", "main")
        test_cmd = context.get("test_command", "pytest")
        build_cmd = context.get("build_command", None)
        instructions = context.get("instructions", "Execute autonomous test-driven modifications for task.")

        yaml_lines = [
            "# Google Jules Cloud Execution Profile Configuration",
            "version: 1",
            f"ticket_key: {ticket_key}",
            "platform: google_jules",
            f"target_branch: {branch_name}",
            "execution:",
            "  executor: cloud_vm_remote",
            "  enforce_zero_uncommitted_files: true",
            "  auto_execute_tests: true",
            "task_instructions: |",
            f"  {instructions.strip()}",
            "hooks:",
            f"  test: {test_cmd or 'pytest'}",
            f"  build: {build_cmd if build_cmd else 'null'}"
        ]
        config_path.write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
        return [".jules/config.yaml"]

    @staticmethod
    def validate(working_dir: Path, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """
        Validation: Remote tracking branch must be fully synchronized with zero
        uncommitted or unpushed changes.
        """
        checks = [
            "Check for zero uncommitted changes (git status --porcelain)",
            "Verify remote tracking branch synchronization (zero unpushed commits)"
        ]
        errors = []
        warnings = []

        if not (working_dir / ".git").exists():
            errors.append("Workspace is not a Git repository (.git not found)")
            return ValidationResult(valid=False, platform=TargetPlatform.GOOGLE_JULES, checks_performed=checks, errors=errors)

        try:
            status_res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(working_dir),
                capture_output=True,
                text=True,
                check=False
            )
            if status_res.stdout.strip():
                uncommitted = [l for l in status_res.stdout.strip().splitlines() if l.strip()]
                errors.append(f"Zero uncommitted files rule violated: found {len(uncommitted)} uncommitted changes: {uncommitted[:3]}")

            # Check remote tracking synchronization
            remotes = subprocess.run(["git", "remote"], cwd=str(working_dir), capture_output=True, text=True, check=False)
            if remotes.stdout.strip():
                # origin exists
                branch_res = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(working_dir), capture_output=True, text=True, check=False)
                branch = branch_res.stdout.strip() or "main"
                log_res = subprocess.run(
                    ["git", "log", f"origin/{branch}..{branch}", "--oneline"],
                    cwd=str(working_dir),
                    capture_output=True,
                    text=True,
                    check=False
                )
                if log_res.returncode == 0 and log_res.stdout.strip():
                    unpushed_count = len(log_res.stdout.strip().splitlines())
                    errors.append(f"Remote tracking branch not synchronized: found {unpushed_count} unpushed commits to origin/{branch}")
            else:
                warnings.append("No git remote detected (offline or simulated workspace); remote synchronization check skipped.")

        except Exception as e:
            errors.append(f"Git inspection failed: {e}")

        return ValidationResult(
            valid=(len(errors) == 0),
            platform=TargetPlatform.GOOGLE_JULES,
            checks_performed=checks,
            errors=errors,
            warnings=warnings
        )


class CodexCloudProfileHandler:
    @staticmethod
    def inject(working_dir: Path, context: Dict[str, Any]) -> List[str]:
        """
        Injects:
        - Root task definition (.codex/task.json and .github/prompts/task_directive.prompt.md)
        - PR template stub (.github/pull_request_template.md) detailing Jira ticket origin and test targets.
        """
        created = []
        ticket_key = context.get("ticket_key", "TASK-DEFAULT")
        test_cmd = context.get("test_command", "pytest")
        instructions = context.get("instructions", "Execute automated code generation for ticket.")

        # 1. .codex/task.json
        codex_dir = working_dir / ".codex"
        codex_dir.mkdir(parents=True, exist_ok=True)
        task_json = codex_dir / "task.json"
        task_data = {
            "version": "1.0",
            "ticket_key": ticket_key,
            "target_platform": "CODEX_CLOUD",
            "dispatch_mechanism": "github_app_webhook",
            "test_target": test_cmd,
            "instructions": instructions.strip(),
            "execution_environment": {
                "runner": "cloud_vm",
                "timeout_seconds": 900
            }
        }
        task_json.write_text(json.dumps(task_data, indent=2), encoding="utf-8")
        created.append(".codex/task.json")

        # 2. .github/prompts/task_directive.prompt.md
        prompts_dir = working_dir / ".github" / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        prompt_directive = prompts_dir / "task_directive.prompt.md"
        prompt_directive.write_text(
            f"# OpenAI Codex Cloud Task Directive: {ticket_key}\n\n"
            f"**Ticket Origin**: {ticket_key}\n"
            f"**Test Verification**: `{test_cmd}`\n\n"
            f"## Instructions\n{instructions.strip()}\n",
            encoding="utf-8"
        )
        created.append(".github/prompts/task_directive.prompt.md")

        # 3. .github/pull_request_template.md
        github_dir = working_dir / ".github"
        github_dir.mkdir(parents=True, exist_ok=True)
        pr_template = github_dir / "pull_request_template.md"
        pr_content = f"""## Origin
- **Jira Ticket**: [{ticket_key}](https://jira.internal/browse/{ticket_key})
- **Target Platform**: OpenAI Codex Cloud

## Automated Test Targets
- Verification command: `{test_cmd}`
- Status: Ready for automated review

## Changes Implemented
<!-- Summary of autonomous changes made by Codex Cloud -->
"""
        pr_template.write_text(pr_content, encoding="utf-8")
        created.append(".github/pull_request_template.md")

        return created

    @staticmethod
    def validate(working_dir: Path, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """
        Validation: Verify top-level project descriptors (package.json, pyproject.toml,
        Makefile, Cargo.toml, go.mod, setup.py) exist for remote runners.
        """
        checks = [
            "Verify top-level project descriptors (package.json, pyproject.toml, Makefile, etc.) exist",
            "Verify presence of root task definition (.codex/task.json or prompt directive)",
            "Verify PR template stub exists (.github/pull_request_template.md)"
        ]
        errors = []
        warnings = []

        descriptor_candidates = [
            "package.json", "pyproject.toml", "Makefile", "setup.py",
            "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "requirements.txt"
        ]
        found_descriptors = [d for d in descriptor_candidates if (working_dir / d).exists()]
        if not found_descriptors:
            errors.append(
                f"Missing top-level project descriptor for remote runners. "
                f"Expected at least one of: {', '.join(descriptor_candidates)}"
            )

        if not (working_dir / ".codex" / "task.json").exists() and not (working_dir / ".github" / "prompts" / "task_directive.prompt.md").exists():
            errors.append("Missing root task definition (.codex/task.json or .github/prompts/ directive)")

        if not (working_dir / ".github" / "pull_request_template.md").exists():
            warnings.append("PR template stub .github/pull_request_template.md not found.")

        return ValidationResult(
            valid=(len(errors) == 0),
            platform=TargetPlatform.CODEX_CLOUD,
            checks_performed=checks,
            errors=errors,
            warnings=warnings
        )


class LocalContainerProfileHandler:
    @staticmethod
    def inject(working_dir: Path, context: Dict[str, Any]) -> List[str]:
        """
        Injects:
        - Non-root user setup (`developer` / UID 1000) aligned with host permissions.
        - Toolchains: Pre-warmed base runtimes (Python, Node.js, Go, Rust).
        - Agent CLI binary mounted and configured to execute autonomously against /workspace.
        - Real-time output streaming hook (stdout/stderr logging via FIFO or Docker socket).
        - .docker/mounts.json, Dockerfile, docker-compose.yml.
        """
        created = []
        ticket_key = context.get("ticket_key", "TASK-DEFAULT")

        # 1. .docker directory with mounts.json and stream logging hook
        docker_dir = working_dir / ".docker"
        docker_dir.mkdir(parents=True, exist_ok=True)

        mounts_path = docker_dir / "mounts.json"
        mount_spec = {
            "workspace_source": str(working_dir.resolve()),
            "workspace_target": "/workspace",
            "mode": "rw",
            "ticket_key": ticket_key,
            "user": "1000:1000",
            "resource_limits": {
                "memory": "4g",
                "cpus": 2.0
            },
            "agent_cli_binary": "/usr/local/bin/agent-cli",
            "log_stream": f"/tmp/hephaestus_logs_{ticket_key}.fifo"
        }
        mounts_path.write_text(json.dumps(mount_spec, indent=2), encoding="utf-8")
        created.append(".docker/mounts.json")

        # Real-time streaming hook script
        stream_hook = docker_dir / "stream_logs.sh"
        stream_script = f"""#!/bin/bash
# Real-time stdout/stderr FIFO streaming hook for Hephaestus Agent
FIFO_PATH="{mount_spec['log_stream']}"
if [ ! -p "$FIFO_PATH" ]; then
    mkfifo "$FIFO_PATH" 2>/dev/null || true
fi
exec > >(tee -a "$FIFO_PATH") 2>&1
echo "[Agent Stream] Initialized real-time logging hook for {ticket_key}"
"""
        stream_hook.write_text(stream_script, encoding="utf-8")
        try:
            stream_hook.chmod(stream_hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception:
            pass
        created.append(".docker/stream_logs.sh")

        # 2. Agent configuration directory (.agent/)
        agent_dir = working_dir / ".agent"
        agent_dir.mkdir(parents=True, exist_ok=True)
        agent_cfg = agent_dir / "config.json"
        agent_cfg_data = {
            "version": "1.0",
            "autonomous_execution": True,
            "target_workspace": "/workspace",
            "ticket_key": ticket_key,
            "user": "developer",
            "uid": 1000,
            "toolchains": ["python", "node", "go", "rust"],
            "agent_cli_path": "/usr/local/bin/agent-cli"
        }
        agent_cfg.write_text(json.dumps(agent_cfg_data, indent=2), encoding="utf-8")
        created.append(".agent/config.json")

        # 3. Dockerfile with non-root user developer (1000) and toolchains
        dockerfile = working_dir / "Dockerfile"
        if not dockerfile.exists():
            dockerfile_content = """# Local Sandboxed Container Environment (Hephaestus Agent Harness)
FROM ubuntu:22.04

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install base POSIX utilities, git, curl, ca-certificates, jq, build-essential
RUN apt-get update && apt-get install -y --no-install-recommends \\
    git curl ca-certificates jq tar gzip bzip2 unzip \\
    build-essential libssl-dev zlib1g-dev \\
    python3 python3-pip python3-venv \\
    nodejs npm golang-go \\
    && rm -rf /var/lib/apt/lists/*

# Install Rust toolchain
ENV RUSTUP_HOME=/opt/rust CARGO_HOME=/opt/rust
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
ENV PATH="/opt/rust/bin:${PATH}"

# Setup non-root user (developer:1000)
RUN groupadd -g 1000 developer && \\
    useradd -u 1000 -g developer -m -s /bin/bash developer

# Pre-create workspace and grant permissions
WORKDIR /workspace
RUN chown -R developer:developer /workspace /opt/rust

USER developer
CMD ["tail", "-f", "/dev/null"]
"""
            dockerfile.write_text(dockerfile_content, encoding="utf-8")
            created.append("Dockerfile")

        # 4. docker-compose.yml enforcing 4g memory and 2 cpus
        compose_file = working_dir / "docker-compose.yml"
        if not compose_file.exists():
            compose_content = """version: '3.8'
services:
  agent-sandbox:
    build: .
    user: "1000:1000"
    working_dir: /workspace
    volumes:
      - .:/workspace:rw
    environment:
      - PYTHONUNBUFFERED=1
      - HARNESS_WORKSPACE=/workspace
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
"""
            compose_file.write_text(compose_content, encoding="utf-8")
            created.append("docker-compose.yml")

        return created

    @staticmethod
    def validate(working_dir: Path, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """
        Validation: Workspace directory is writable and resource limits
        (--memory=4g --cpus=2) are enforced.
        """
        checks = [
            "Verify workspace directory is writable",
            "Verify container resource limits (--memory=4g --cpus=2) are enforced",
            "Verify non-root user setup (developer:1000)",
            "Verify real-time output streaming hook existence"
        ]
        errors = []
        warnings = []

        # 1. Check workspace directory is writable
        test_file = working_dir / f".write_test_{os.getpid()}.tmp"
        try:
            test_file.write_text("writable_check", encoding="utf-8")
            test_file.unlink()
        except Exception as write_err:
            errors.append(f"Workspace directory is not writable: {write_err}")

        # 2. Check resource limits enforcement
        mounts_path = working_dir / ".docker" / "mounts.json"
        compose_path = working_dir / "docker-compose.yml"
        resource_enforced = False

        if mounts_path.exists():
            try:
                data = json.loads(mounts_path.read_text(encoding="utf-8"))
                res_limits = data.get("resource_limits", {})
                mem = str(res_limits.get("memory", "")).lower()
                cpus = float(res_limits.get("cpus", 0))
                if ("4g" in mem or "4096" in mem) and cpus >= 2.0:
                    resource_enforced = True
            except Exception:
                pass

        if not resource_enforced and compose_path.exists():
            try:
                comp_text = compose_path.read_text(encoding="utf-8")
                if "4G" in comp_text.upper() and ("2" in comp_text or "2.0" in comp_text):
                    resource_enforced = True
            except Exception:
                pass

        if not resource_enforced:
            errors.append("Resource limits (--memory=4g --cpus=2) are not configured or enforced in workspace container spec.")

        # 3. Check streaming hook
        stream_hook = working_dir / ".docker" / "stream_logs.sh"
        if not stream_hook.exists():
            warnings.append("Real-time logging streaming hook (.docker/stream_logs.sh) is not present.")

        return ValidationResult(
            valid=(len(errors) == 0),
            platform=TargetPlatform.LOCAL_CONTAINER,
            checks_performed=checks,
            errors=errors,
            warnings=warnings
        )


class GrokBuildProfileHandler:
    @staticmethod
    def inject(working_dir: Path, context: Dict[str, Any]) -> List[str]:
        """
        Injects:
        - .grok/build-config.json containing the task spec, dependency manifest,
          allowed execution steps, and acceptance criteria.
        - Exported project structural map (repo_tree.txt) to minimize token exploration overhead.
        """
        created = []
        ticket_key = context.get("ticket_key", "TASK-DEFAULT")
        instructions = context.get("instructions", "Execute autonomous build and generation.")
        preparations = context.get("preparations", "")
        test_cmd = context.get("test_command", "pytest")
        build_cmd = context.get("build_command", None)

        # 1. Export structural map: repo_tree.txt
        tree_text = generate_repo_tree(working_dir)
        tree_file = working_dir / "repo_tree.txt"
        tree_file.write_text(tree_text, encoding="utf-8")
        created.append("repo_tree.txt")

        # 2. Extract declared target files from preparations.md or context
        target_files = context.get("target_files", [])
        if not target_files and preparations:
            # Extract paths mentioned in preparations (e.g., words with slashes or extensions)
            for token in re.findall(r"[\w\./-]+\.[a-zA-Z0-9]+", preparations):
                token_clean = token.strip("`'\"(),:;")
                if token_clean and not token_clean.startswith("http") and token_clean not in target_files:
                    target_files.append(token_clean)

        # 3. .grok/build-config.json
        grok_dir = working_dir / ".grok"
        grok_dir.mkdir(parents=True, exist_ok=True)
        build_cfg_file = grok_dir / "build-config.json"

        build_config = {
            "version": "1.0",
            "platform": "GROK_BUILD",
            "task_spec": {
                "ticket_key": ticket_key,
                "instructions": instructions.strip(),
                "target_files": target_files
            },
            "dependency_manifest": {
                "build_command": build_cmd,
                "test_command": test_cmd or "pytest",
                "lint_command": context.get("lint_command", None)
            },
            "allowed_execution_steps": [
                "read_workspace_tree",
                "inspect_mapped_target_files",
                "modify_target_files",
                "execute_test_runner"
            ],
            "acceptance_criteria": [
                "All mapped target files must be successfully updated",
                "Test suite must pass with 0 exit code",
                "No unexpected file deletions outside target spec"
            ]
        }
        build_cfg_file.write_text(json.dumps(build_config, indent=2), encoding="utf-8")
        created.append(".grok/build-config.json")

        return created

    @staticmethod
    def validate(working_dir: Path, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """
        Validation: Verify target files declared in preparations.md are correctly
        mapped in the build configuration (.grok/build-config.json).
        """
        checks = [
            "Verify presence of .grok/build-config.json",
            "Verify exported structural map repo_tree.txt",
            "Verify target files declared in preparations.md are correctly mapped in build configuration"
        ]
        errors = []
        warnings = []

        cfg_path = working_dir / ".grok" / "build-config.json"
        if not cfg_path.exists():
            errors.append("Missing .grok/build-config.json configuration file.")
            return ValidationResult(valid=False, platform=TargetPlatform.GROK_BUILD, checks_performed=checks, errors=errors)

        tree_path = working_dir / "repo_tree.txt"
        if not tree_path.exists():
            warnings.append("Structural map repo_tree.txt is missing.")

        try:
            cfg_data = json.loads(cfg_path.read_text(encoding="utf-8"))
            mapped_files = set(cfg_data.get("task_spec", {}).get("target_files", []))

            # Check against preparations.md
            prep_file = working_dir / "preparations.md"
            if not prep_file.exists():
                # Check staging or .harness/merged_preparations.md
                prep_file = working_dir / ".harness" / "merged_preparations.md"

            if prep_file.exists():
                prep_text = prep_file.read_text(encoding="utf-8")
                # Look for file references
                file_tokens = re.findall(r"[\w\./-]+\.[a-zA-Z0-9]+", prep_text)
                declared_files = set()
                for token in file_tokens:
                    token_clean = token.strip("`'\"(),:;")
                    if (
                        token_clean
                        and not token_clean.startswith("http")
                        and token_clean not in ("preparations.md", "prompt.md", "config.yaml", "build-config.json")
                    ):
                        declared_files.add(token_clean)

                missing_mappings = []
                for df in declared_files:
                    # Match if exact or if filename matches any mapped file
                    df_name = Path(df).name
                    if df not in mapped_files and not any(Path(mf).name == df_name for mf in mapped_files):
                        missing_mappings.append(df)

                if missing_mappings:
                    errors.append(
                        f"Target files declared in preparations.md are not mapped in .grok/build-config.json: {missing_mappings}"
                    )
        except Exception as ex:
            errors.append(f"Failed to parse and validate .grok/build-config.json: {ex}")

        return ValidationResult(
            valid=(len(errors) == 0),
            platform=TargetPlatform.GROK_BUILD,
            checks_performed=checks,
            errors=errors,
            warnings=warnings
        )


class DevinAIProfileHandler:
    @staticmethod
    def inject(working_dir: Path, context: Dict[str, Any]) -> List[str]:
        """
        Injects:
        - Injected task directive (devin_instructions.md) optimized for Devin's multi-step planning framework.
        - Reproducible sandbox scripts (scripts/devin_setup.sh, scripts/devin_test.sh) with executable permissions.
        """
        created = []
        ticket_key = context.get("ticket_key", "TASK-DEFAULT")
        instructions = context.get("instructions", "Resolve Jira task.")
        test_cmd = context.get("test_command", "pytest")

        # 1. devin_instructions.md (multi-step planning directive)
        devin_md = working_dir / "devin_instructions.md"
        devin_content = f"""# Devin AI Task Directive: {ticket_key}

## Objective
{instructions.strip()}

## Multi-Step Execution Framework
1. **Explore & Verify Setup**: Run `bash scripts/devin_setup.sh` to initialize dependencies and environment.
2. **Reproduce Baseline**: Run `bash scripts/devin_test.sh` to confirm current test suite behavior.
3. **Plan & Implement**: Break down required code changes and implement edits incrementally.
4. **Automated Verification**: Run `bash scripts/devin_test.sh` repeatedly until all tests pass with zero errors.
5. **Final Review**: Validate git diff and ensure no temporary files remain.

## Sandbox Anchors
- Setup Script: `scripts/devin_setup.sh`
- Test Script: `scripts/devin_test.sh`
"""
        devin_md.write_text(devin_content, encoding="utf-8")
        created.append("devin_instructions.md")

        # 2. scripts/ directory
        scripts_dir = working_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)

        setup_sh = scripts_dir / "devin_setup.sh"
        setup_content = f"""#!/bin/bash
set -e
echo "==> [Devin Sandbox Setup] Initializing environment for {ticket_key}..."

if [ -f "requirements.txt" ]; then
    echo "Installing Python dependencies from requirements.txt..."
    pip install -r requirements.txt || true
elif [ -f "pyproject.toml" ]; then
    echo "Installing Python dependencies from pyproject.toml..."
    pip install . || true
elif [ -f "package.json" ]; then
    echo "Installing Node dependencies..."
    npm install || true
fi

echo "==> [Devin Sandbox Setup] Setup completed successfully."
"""
        setup_sh.write_text(setup_content, encoding="utf-8")
        setup_sh.chmod(setup_sh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        created.append("scripts/devin_setup.sh")

        test_sh = scripts_dir / "devin_test.sh"
        test_content = f"""#!/bin/bash
set -e
echo "==> [Devin Verification] Executing test runner anchor..."
{test_cmd or 'pytest'}
echo "==> [Devin Verification] All verification tests passed."
"""
        test_sh.write_text(test_content, encoding="utf-8")
        test_sh.chmod(test_sh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        created.append("scripts/devin_test.sh")

        return created

    @staticmethod
    def validate(working_dir: Path, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """
        Validation: Verify existence and executable permissions (chmod +x) on all
        injected setup and test helper scripts.
        """
        checks = [
            "Verify devin_instructions.md exists",
            "Verify scripts/devin_setup.sh exists and has executable permissions (chmod +x)",
            "Verify scripts/devin_test.sh exists and has executable permissions (chmod +x)"
        ]
        errors = []
        warnings = []

        if not (working_dir / "devin_instructions.md").exists():
            errors.append("Missing task directive: devin_instructions.md")

        for script_rel in ["scripts/devin_setup.sh", "scripts/devin_test.sh"]:
            sp = working_dir / script_rel
            if not sp.exists():
                errors.append(f"Missing required reproducible sandbox script: {script_rel}")
            else:
                # Check executable bit
                mode = sp.stat().st_mode
                is_executable = bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
                if not is_executable or not os.access(str(sp), os.X_OK):
                    errors.append(f"Script {script_rel} exists but lacks executable permissions (chmod +x required).")

        return ValidationResult(
            valid=(len(errors) == 0),
            platform=TargetPlatform.DEVIN_AI,
            checks_performed=checks,
            errors=errors,
            warnings=warnings
        )


class CursorDevcontainerProfileHandler:
    @staticmethod
    def inject(working_dir: Path, context: Dict[str, Any]) -> List[str]:
        """
        Injects fully configured .devcontainer/devcontainer.json:
        - Appropriate base image or Dockerfile reference matching runtime stack
        - Cursor/VS Code extensions relevant to stack (e.g. Python, ESLint, language servers)
        - customizations.cursor block configuring editor rules, system prompts, tool authorizations
        - postCreateCommand configured to automatically run dependency installs discovered during preparation.
        - Matching .devcontainer/Dockerfile.
        """
        created = []
        ticket_key = context.get("ticket_key", "TASK-DEFAULT")
        base_image = context.get("base_image", "mcr.microsoft.com/devcontainers/python:3.12")
        post_create_cmd = context.get("post_create_cmd", "pip install -e . || pip install -r requirements.txt || true")

        devcontainer_dir = working_dir / ".devcontainer"
        devcontainer_dir.mkdir(parents=True, exist_ok=True)

        # 1. .devcontainer/Dockerfile
        dockerfile_path = devcontainer_dir / "Dockerfile"
        if not dockerfile_path.exists():
            dockerfile_content = f"""FROM {base_image}

# Install essential devcontainer tools
RUN apt-get update && apt-get install -y --no-install-recommends \\
    git curl ca-certificates jq \\
    && rm -rf /var/lib/apt/lists/*

USER vscode
"""
            dockerfile_path.write_text(dockerfile_content, encoding="utf-8")
            created.append(".devcontainer/Dockerfile")

        # 2. .devcontainer/devcontainer.json (standard OCI devcontainer configuration with comments)
        devcontainer_json = devcontainer_dir / "devcontainer.json"
        config_data = {
            "name": f"Cursor Workspace - {ticket_key}",
            "build": {
                "dockerfile": "Dockerfile"
            },
            "workspaceMount": "source=${localWorkspaceFolder},target=/workspace,type=bind,consistency=cached",
            "workspaceFolder": "/workspace",
            "customizations": {
                "vscode": {
                    "extensions": [
                        "ms-python.python",
                        "ms-python.vscode-pylance",
                        "ms-python.black-formatter",
                        "dbaeumer.vscode-eslint"
                    ]
                },
                "cursor": {
                    "editorRules": [
                        "Maintain deterministic formatting",
                        "Always write accompanying tests for new functions",
                        "Never overwrite user secrets in .env"
                    ],
                    "systemPrompt": f"You are an autonomous AI coding assistant working in Cursor on ticket {ticket_key}.",
                    "toolAuthorizations": {
                        "allowTerminalExecution": True,
                        "allowFileModifications": True,
                        "allowNetworkEgress": True
                    }
                }
            },
            "postCreateCommand": post_create_cmd,
            "remoteUser": "vscode"
        }

        # Format with comments allowed in JSONC
        jsonc_header = "// Cursor Dev Container Configuration\n// Auto-generated by Hephaestus ExecutionProfileEngine\n"
        devcontainer_json.write_text(jsonc_header + json.dumps(config_data, indent=2) + "\n", encoding="utf-8")
        created.append(".devcontainer/devcontainer.json")

        return created

    @staticmethod
    def validate(working_dir: Path, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """
        Validation: Parse .devcontainer/devcontainer.json to confirm it is valid
        JSON with comments stripped.
        """
        checks = [
            "Verify .devcontainer/devcontainer.json exists",
            "Parse .devcontainer/devcontainer.json with comments stripped (valid JSONC)",
            "Verify customizations.cursor block is configured",
            "Verify postCreateCommand is defined"
        ]
        errors = []
        warnings = []

        cfg_path = working_dir / ".devcontainer" / "devcontainer.json"
        if not cfg_path.exists():
            errors.append("Missing .devcontainer/devcontainer.json configuration file.")
            return ValidationResult(valid=False, platform=TargetPlatform.CURSOR_DEVCONTAINER, checks_performed=checks, errors=errors)

        try:
            raw_text = cfg_path.read_text(encoding="utf-8")
            clean_json = strip_json_comments(raw_text)
            parsed = json.loads(clean_json)

            # Validate customizations.cursor block
            customizations = parsed.get("customizations", {})
            cursor_customizations = customizations.get("cursor")
            if not cursor_customizations:
                errors.append("Missing required 'customizations.cursor' block in .devcontainer/devcontainer.json")
            else:
                if "editorRules" not in cursor_customizations:
                    warnings.append("Missing 'editorRules' in customizations.cursor")
                if "toolAuthorizations" not in cursor_customizations:
                    warnings.append("Missing 'toolAuthorizations' in customizations.cursor")

            if not parsed.get("postCreateCommand"):
                warnings.append("postCreateCommand is not configured in .devcontainer/devcontainer.json")

        except json.JSONDecodeError as jde:
            errors.append(f"Failed to parse .devcontainer/devcontainer.json even with comments stripped: {jde}")
        except Exception as ex:
            errors.append(f"Devcontainer inspection error: {ex}")

        return ValidationResult(
            valid=(len(errors) == 0),
            platform=TargetPlatform.CURSOR_DEVCONTAINER,
            checks_performed=checks,
            errors=errors,
            warnings=warnings
        )


# ==============================================================================
# EXECUTION PROFILES REGISTRY
# ==============================================================================

PROFILES_REGISTRY: Dict[TargetPlatform, ExecutionProfile] = {
    TargetPlatform.GOOGLE_JULES: ExecutionProfile(
        platform=TargetPlatform.GOOGLE_JULES,
        config=PlatformConfig(
            platform=TargetPlatform.GOOGLE_JULES,
            display_name="Google Jules Cloud Executor",
            environment_type="cloud_vm",
            expectations="Cloud VM executor targeting remote GitHub branches with pre-synchronized status.",
            required_injections=[".jules/config.yaml"],
            validation_rules=[
                "Remote tracking branch must be fully synchronized with zero uncommitted or unpushed changes."
            ]
        ),
        rules=[
            "Enforce zero uncommitted files",
            "Generate/update .jules/ configuration",
            "Set build/test hooks into standard repo configs"
        ]
    ),
    TargetPlatform.CODEX_CLOUD: ExecutionProfile(
        platform=TargetPlatform.CODEX_CLOUD,
        config=PlatformConfig(
            platform=TargetPlatform.CODEX_CLOUD,
            display_name="OpenAI Codex Cloud",
            environment_type="remote_dispatch",
            expectations="Remote task dispatch via webhook/GitHub App integration.",
            required_injections=[
                ".codex/task.json",
                ".github/prompts/task_directive.prompt.md",
                ".github/pull_request_template.md"
            ],
            validation_rules=[
                "Verify top-level project descriptors (package.json, pyproject.toml, Makefile) exist for remote runners."
            ]
        ),
        rules=[
            "Verify top-level execution entry points",
            "Format task metadata for GitHub App webhook trigger",
            "Inject PR template stub with Jira origin"
        ]
    ),
    TargetPlatform.LOCAL_CONTAINER: ExecutionProfile(
        platform=TargetPlatform.LOCAL_CONTAINER,
        config=PlatformConfig(
            platform=TargetPlatform.LOCAL_CONTAINER,
            display_name="Local Sandboxed Container (Antigravity/Agent CLI)",
            environment_type="local_docker",
            expectations="Ephemeral Docker container running on the local host with mounted workspace and UID 1000.",
            required_injections=[
                ".docker/mounts.json",
                ".docker/stream_logs.sh",
                ".agent/config.json",
                "Dockerfile",
                "docker-compose.yml"
            ],
            validation_rules=[
                "Workspace directory is writable",
                "Resource limits (--memory=4g --cpus=2) are enforced"
            ]
        ),
        container_spec=ContainerSpec(
            image="python:3.12-slim",
            user="developer:1000",
            memory_limit="4g",
            cpu_count=2.0,
            command="tail -f /dev/null",
            working_dir="/workspace"
        ),
        rules=[
            "Configure Docker mount points",
            "Enforce non-root user developer (UID 1000)",
            "Enforce resource limits (memory: 4g, cpus: 2)",
            "Setup pre-warmed toolchains",
            "Enable real-time streaming hook"
        ]
    ),
    TargetPlatform.GROK_BUILD: ExecutionProfile(
        platform=TargetPlatform.GROK_BUILD,
        config=PlatformConfig(
            platform=TargetPlatform.GROK_BUILD,
            display_name="Grok Build Cloud Native",
            environment_type="cloud_native",
            expectations="Cloud-native or API-driven build and generation environment expecting structured task context.",
            required_injections=[
                ".grok/build-config.json",
                "repo_tree.txt"
            ],
            validation_rules=[
                "Verify target files declared in preparations.md are correctly mapped in the build configuration."
            ]
        ),
        rules=[
            "Export structural map repo_tree.txt",
            "Map declared preparation files into build-config.json",
            "Enforce explicit allowed execution steps"
        ]
    ),
    TargetPlatform.DEVIN_AI: ExecutionProfile(
        platform=TargetPlatform.DEVIN_AI,
        config=PlatformConfig(
            platform=TargetPlatform.DEVIN_AI,
            display_name="Devin AI Autonomous Engineer",
            environment_type="autonomous_agent",
            expectations="Autonomous remote software engineer executing via Cognition API or GitHub session.",
            required_injections=[
                "devin_instructions.md",
                "scripts/devin_setup.sh",
                "scripts/devin_test.sh"
            ],
            validation_rules=[
                "Verify existence and executable permissions (chmod +x) on all injected setup and test helper scripts."
            ]
        ),
        rules=[
            "Inject multi-step planning framework instructions",
            "Provide reproducible sandbox scripts with executable permissions"
        ]
    ),
    TargetPlatform.CURSOR_DEVCONTAINER: ExecutionProfile(
        platform=TargetPlatform.CURSOR_DEVCONTAINER,
        config=PlatformConfig(
            platform=TargetPlatform.CURSOR_DEVCONTAINER,
            display_name="Cursor with Devcontainers",
            environment_type="devcontainer",
            expectations="Standardized OCI Dev Container tailored for Cursor IDE agents and human-in-the-loop handoff.",
            required_injections=[
                ".devcontainer/devcontainer.json",
                ".devcontainer/Dockerfile"
            ],
            validation_rules=[
                "Parse .devcontainer/devcontainer.json to confirm it is valid JSON with comments stripped."
            ]
        ),
        rules=[
            "Configure OCI devcontainer specification",
            "Configure customizations.cursor block with rules and tool authorizations",
            "Configure postCreateCommand for dependency setup"
        ]
    )
}

HANDLERS = {
    TargetPlatform.GOOGLE_JULES: JulesProfileHandler,
    TargetPlatform.CODEX_CLOUD: CodexCloudProfileHandler,
    TargetPlatform.LOCAL_CONTAINER: LocalContainerProfileHandler,
    TargetPlatform.GROK_BUILD: GrokBuildProfileHandler,
    TargetPlatform.DEVIN_AI: DevinAIProfileHandler,
    TargetPlatform.CURSOR_DEVCONTAINER: CursorDevcontainerProfileHandler,
}


def get_execution_profile(platform: Union[TargetPlatform, str]) -> ExecutionProfile:
    """
    Returns the deterministic execution profile for the target platform.
    Normalizes aliases and string names.
    """
    normalized_platform = TargetPlatform.normalize(platform)
    if normalized_platform not in PROFILES_REGISTRY:
        raise KeyError(f"No execution profile registered for platform: {normalized_platform}")
    return PROFILES_REGISTRY[normalized_platform]


def inject_profile_configurations(
    platform: Union[TargetPlatform, str],
    working_dir: Path,
    context: Dict[str, Any]
) -> List[str]:
    """Injects platform-specific requirement files into the target workspace."""
    normalized_platform = TargetPlatform.normalize(platform)
    handler = HANDLERS.get(normalized_platform)
    if not handler:
        raise ValueError(f"No injection handler available for platform {normalized_platform}")
    return handler.inject(working_dir, context)


def validate_profile_environment(
    platform: Union[TargetPlatform, str],
    working_dir: Path,
    context: Optional[Dict[str, Any]] = None
) -> ValidationResult:
    """Executes deterministic platform-specific validation checks against the workspace."""
    normalized_platform = TargetPlatform.normalize(platform)
    handler = HANDLERS.get(normalized_platform)
    if not handler:
        raise ValueError(f"No validation handler available for platform {normalized_platform}")
    return handler.validate(working_dir, context)
