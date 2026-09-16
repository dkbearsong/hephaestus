import os
from pathlib import Path
from typing import Callable, List, Dict, Any, Optional
from pydantic import BaseModel, Field


class AgentSpec(BaseModel):
    """
    Profile definition for a containerized coding agent runtime engine.
    """
    name: str = Field(description="Unique agent name, e.g., 'antigravity', 'claude_code', 'aider', 'custom'")
    docker_image: str = Field(description="Target base image with pre-installed agent dependencies")
    entrypoint_cmd: Callable[[Path, str], List[str]] = Field(
        description="Generates the CLI command injecting autonomous flags, e.g., --non-interactive, --auto-confirm"
    )
    env_overrides: Dict[str, str] = Field(
        default_factory=dict,
        description="Injected API keys, model targets, and telemetry hooks"
    )

    class Config:
        arbitrary_types_allowed = True


def default_antigravity_cmd(workspace_dir: Path, prompt_file: str) -> List[str]:
    return [
        "antigravity",
        "run",
        "--non-interactive",
        "--auto-confirm",
        "--workspace",
        str(workspace_dir),
        "--prompt-file",
        prompt_file
    ]


def default_claude_code_cmd(workspace_dir: Path, prompt_file: str) -> List[str]:
    return [
        "claude",
        "--dangerously-skip-permissions",
        "--non-interactive",
        "-p",
        prompt_file
    ]


def default_aider_cmd(workspace_dir: Path, prompt_file: str) -> List[str]:
    return [
        "aider",
        "--yes-always",
        "--no-auto-commits",
        "--message-file",
        prompt_file
    ]


def default_custom_cmd(workspace_dir: Path, prompt_file: str) -> List[str]:
    return [
        "python3",
        "-m",
        "agent_runner",
        "--auto-approve",
        "--workspace",
        str(workspace_dir),
        "--prompt",
        prompt_file
    ]


class AgentRegistry:
    """
    Registry for swappable agent runtime specs.
    """

    def __init__(self):
        self._registry: Dict[str, AgentSpec] = {}
        self._register_default_profiles()

    def _register_default_profiles(self):
        self.register(
            AgentSpec(
                name="antigravity",
                docker_image="hephaestus/agent-antigravity:latest",
                entrypoint_cmd=default_antigravity_cmd,
                env_overrides={"AGENT_NAME": "antigravity", "AUTO_APPROVE": "1"}
            )
        )
        self.register(
            AgentSpec(
                name="claude_code",
                docker_image="hephaestus/agent-claude-code:latest",
                entrypoint_cmd=default_claude_code_cmd,
                env_overrides={"AGENT_NAME": "claude_code", "CLAUDE_AUTO_APPROVE": "1"}
            )
        )
        self.register(
            AgentSpec(
                name="aider",
                docker_image="hephaestus/agent-aider:latest",
                entrypoint_cmd=default_aider_cmd,
                env_overrides={"AGENT_NAME": "aider", "AIDER_YES": "1"}
            )
        )
        self.register(
            AgentSpec(
                name="custom",
                docker_image="hephaestus/agent-custom:latest",
                entrypoint_cmd=default_custom_cmd,
                env_overrides={"AGENT_NAME": "custom", "NON_INTERACTIVE": "1"}
            )
        )

    def register(self, spec: AgentSpec):
        self._registry[spec.name.lower()] = spec

    def get(self, name: str) -> AgentSpec:
        key = name.lower() if name else "custom"
        if key in self._registry:
            return self._registry[key]

        # Return fallback custom spec with requested name
        return AgentSpec(
            name=key,
            docker_image=f"hephaestus/agent-{key}:latest",
            entrypoint_cmd=default_custom_cmd,
            env_overrides={"AGENT_NAME": key, "NON_INTERACTIVE": "1"}
        )

    def list_specs(self) -> List[str]:
        return list(self._registry.keys())


agent_registry = AgentRegistry()
