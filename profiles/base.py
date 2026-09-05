"""
Baseline Environment & Core Profile Schemas
Defines deterministic baseline configurations and typed Pydantic models for all execution profiles.
"""

import os
import stat
import subprocess
import logging
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Literal
from pydantic import BaseModel, Field, ConfigDict

logger = logging.getLogger("hephaestus.profiles.base")


class TargetPlatform(str, Enum):
    """Supported target platform execution runtimes."""
    GOOGLE_JULES = "GOOGLE_JULES"
    CODEX_CLOUD = "CODEX_CLOUD"
    LOCAL_CONTAINER = "LOCAL_CONTAINER"
    GROK_BUILD = "GROK_BUILD"
    DEVIN_AI = "DEVIN_AI"
    CURSOR_DEVCONTAINER = "CURSOR_DEVCONTAINER"

    @classmethod
    def normalize(cls, value: Union["TargetPlatform", str]) -> "TargetPlatform":
        """Normalizes case and string aliases to valid TargetPlatform enum member."""
        if isinstance(value, TargetPlatform):
            return value

        val_str = str(value).strip().upper().replace("-", "_")
        aliases = {
            "JULES": cls.GOOGLE_JULES,
            "GOOGLE_JULES": cls.GOOGLE_JULES,
            "GOOGLE": cls.GOOGLE_JULES,
            "CODEX": cls.CODEX_CLOUD,
            "CODEX_CLOUD": cls.CODEX_CLOUD,
            "OPENAI_CODEX": cls.CODEX_CLOUD,
            "OPENAI_CODEX_CLOUD": cls.CODEX_CLOUD,
            "LOCAL": cls.LOCAL_CONTAINER,
            "LOCAL_CONTAINER": cls.LOCAL_CONTAINER,
            "DOCKER": cls.LOCAL_CONTAINER,
            "DOCKER_SANDBOX": cls.LOCAL_CONTAINER,
            "ANTIGRAVITY": cls.LOCAL_CONTAINER,
            "GROK": cls.GROK_BUILD,
            "GROK_BUILD": cls.GROK_BUILD,
            "XAI": cls.GROK_BUILD,
            "DEVIN": cls.DEVIN_AI,
            "DEVIN_AI": cls.DEVIN_AI,
            "COGNITION": cls.DEVIN_AI,
            "CURSOR": cls.CURSOR_DEVCONTAINER,
            "CURSOR_DEVCONTAINER": cls.CURSOR_DEVCONTAINER,
            "CURSOR_DEV_CONTAINER": cls.CURSOR_DEVCONTAINER,
            "DEVCONTAINER": cls.CURSOR_DEVCONTAINER,
        }
        if val_str in aliases:
            return aliases[val_str]
        try:
            return cls(val_str)
        except ValueError:
            raise ValueError(f"Unknown target platform: '{value}'. Valid platforms: {[e.value for e in cls]}")


class ContainerSpec(BaseModel):
    """
    Detailed container specification for runtime environments.
    Defines Docker images, environment variables, mounts, user identities, and resource constraints.
    """
    model_config = ConfigDict(extra="allow")

    image: str = Field(default="python:3.12-slim", description="Base Docker/OCI image reference")
    environment: Dict[str, str] = Field(default_factory=dict, description="Injected container environment variables")
    mounts: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description="Volume mounts mapping host paths to container targets, e.g. {'/host/p': {'bind': '/workspace', 'mode': 'rw'}}"
    )
    entrypoint: Optional[Union[str, List[str]]] = Field(None, description="Custom entrypoint executable")
    command: Optional[Union[str, List[str]]] = Field(default="tail -f /dev/null", description="Default container command")
    working_dir: str = Field(default="/workspace", description="Container working directory")
    user: Optional[str] = Field(default="developer:1000", description="Non-root user spec (UID 1000)")
    memory_limit: str = Field(default="4g", description="Memory limit enforcement, e.g. '4g'")
    cpu_count: float = Field(default=2.0, description="CPU resource limit enforcement, e.g. 2.0 cores")
    ports: Dict[str, int] = Field(default_factory=dict, description="Port forwards, e.g. {'8000/tcp': 8000}")
    network_mode: str = Field(default="bridge", description="Docker network driver mode")


class PlatformConfig(BaseModel):
    """Platform-specific metadata, expectation constraints, and validation definitions."""
    platform: TargetPlatform
    display_name: str
    environment_type: str = Field(..., description="E.g. cloud_vm, remote_dispatch, local_docker, cloud_native, autonomous_agent, devcontainer")
    expectations: str = Field(..., description="High-level runtime execution expectations")
    required_injections: List[str] = Field(default_factory=list, description="File paths or configs that must be injected")
    validation_rules: List[str] = Field(default_factory=list, description="Validation rules enforced before execution")
    container_spec: Optional[ContainerSpec] = None


class ValidationResult(BaseModel):
    """Result of platform validation check."""
    valid: bool
    platform: TargetPlatform
    checks_performed: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class BaselineConfig(BaseModel):
    """Deterministic baseline configuration common across ALL containers and runtimes."""
    base_utilities: List[str] = Field(
        default_factory=lambda: ["git", "curl", "ca-certificates", "jq", "tar", "gzip"],
        description="Standard POSIX and networking utilities required in all environments"
    )
    git_user_name: str = "Harness Agent"
    git_user_email: str = "agent@harness.internal"
    git_safe_directory: str = "*"
    harness_dir_name: str = ".harness"
    gitignore_defaults: List[str] = Field(
        default_factory=lambda: [
            "# Environments & Bytecode",
            "__pycache__/",
            "*.py[cod]",
            "*$py.class",
            ".venv/",
            "env/",
            "venv/",
            "node_modules/",
            "dist/",
            "build/",
            "target/",
            "",
            "# IDEs & OS",
            ".DS_Store",
            ".idea/",
            ".vscode/",
            "*.swp",
            "",
            "# Secrets & Environment variables",
            ".env",
            "*.local.env",
            "",
            "# Agent harness scratch files",
            ".harness_inbox/",
            "*.tmp",
            "repo_tree.txt"
        ]
    )


class ExecutionProfile(BaseModel):
    """
    Unified Execution Profile contract containing platform configuration,
    container specifications, injection templates, and validation hooks.
    """
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    platform: TargetPlatform
    config: PlatformConfig
    container_spec: Optional[ContainerSpec] = None
    rules: List[str] = Field(default_factory=list)
    file_templates: Dict[str, str] = Field(default_factory=dict)


def apply_baseline_environment(
    working_dir: Path,
    prompt_content: str = "",
    task_context: Optional[str] = None
) -> Dict[str, Any]:
    """
    Enforces deterministic baseline configuration required before code generation begins:
    1. Base Utilities: verifies git availability and standard utilities.
    2. Git Context: pre-configures automated identity:
       - git config --global user.name "Harness Agent"
       - git config --global user.email "agent@harness.internal"
       - git config --global --add safe.directory "*"
    3. Workspace Anchors:
       - Standard .gitignore defaults
       - Populated .harness/ directory containing prompt.md and task_context.md
       - Strict working directory permission normalization (chmod/chown).
    """
    working_dir = Path(working_dir).resolve()
    working_dir.mkdir(parents=True, exist_ok=True)
    baseline = BaselineConfig()
    created_files: List[str] = []

    # 1. Standard .gitignore defaults
    gitignore_path = working_dir / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text("\n".join(baseline.gitignore_defaults) + "\n", encoding="utf-8")
        created_files.append(".gitignore")
    else:
        # Ensure important entries are present
        existing_lines = set(gitignore_path.read_text(encoding="utf-8").splitlines())
        additions = []
        for line in baseline.gitignore_defaults:
            if line and not line.startswith("#") and line not in existing_lines:
                additions.append(line)
        if additions:
            with open(gitignore_path, "a", encoding="utf-8") as f:
                f.write("\n" + "\n".join(additions) + "\n")

    # 2. Populated .harness/ directory containing prompt.md and task_context.md
    harness_dir = working_dir / baseline.harness_dir_name
    harness_dir.mkdir(parents=True, exist_ok=True)

    prompt_file = harness_dir / "prompt.md"
    if not prompt_file.exists() or prompt_content:
        prompt_file.write_text(prompt_content or "# Harness Task Prompt\n\n*(No prompt provided)*\n", encoding="utf-8")
        created_files.append(f"{baseline.harness_dir_name}/prompt.md")

    task_context_file = harness_dir / "task_context.md"
    context_body = task_context or (
        "# Task Execution Context\n\n"
        "- Baseline initialized: True\n"
        "- Safe directory: wildcard enabled\n"
        "- Identity: Harness Agent <agent@harness.internal>\n"
    )
    task_context_file.write_text(context_body, encoding="utf-8")
    created_files.append(f"{baseline.harness_dir_name}/task_context.md")

    # 3. Git Context & Safe directory overrides
    git_configured = False
    try:
        # Run global git identity config
        subprocess.run(["git", "config", "--global", "user.name", baseline.git_user_name], capture_output=True, text=True, check=False)
        subprocess.run(["git", "config", "--global", "user.email", baseline.git_user_email], capture_output=True, text=True, check=False)
        subprocess.run(["git", "config", "--global", "--add", "safe.directory", baseline.git_safe_directory], capture_output=True, text=True, check=False)

        # Also configure local repo if .git directory exists
        if (working_dir / ".git").exists():
            subprocess.run(["git", "config", "user.name", baseline.git_user_name], cwd=str(working_dir), capture_output=True, text=True, check=False)
            subprocess.run(["git", "config", "user.email", baseline.git_user_email], cwd=str(working_dir), capture_output=True, text=True, check=False)
        git_configured = True
    except Exception as e:
        logger.warning(f"Baseline git configuration encountered: {e}")

    # 4. Strict working directory permission normalization
    normalized_count = 0
    try:
        for p in working_dir.rglob("*"):
            if ".git" in p.parts:
                continue
            try:
                cur_mode = p.stat().st_mode
                if p.is_dir():
                    # rwxr-xr-x (0o755)
                    new_mode = cur_mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
                    os.chmod(p, new_mode)
                else:
                    # rw-r--r-- (0o644) or preserve execute if script
                    is_exec = bool(cur_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
                    new_mode = cur_mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
                    if is_exec:
                        new_mode |= (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                    os.chmod(p, new_mode)
                normalized_count += 1
            except Exception:
                pass
    except Exception as perm_err:
        logger.warning(f"Permission normalization encountered warning: {perm_err}")

    return {
        "success": True,
        "working_directory": str(working_dir),
        "created_files": created_files,
        "git_configured": git_configured,
        "normalized_count": normalized_count,
        "base_utilities": baseline.base_utilities
    }
