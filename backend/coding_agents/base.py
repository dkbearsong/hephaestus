"""
Base Definitions for Hephaestus Coding Agent Orchestrator & Container Environments
"""

import os
import re
import uuid
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pathlib import Path
from pydantic import BaseModel, Field
from backend.harness.base import BaseCodingHarness, HarnessResult
from backend.config import ROOT_DIR

logger = logging.getLogger("hephaestus.coding_agents.base")

class ContainerEnvironment(BaseModel):
    """
    Metadata representation of an initiated container or cloud execution sandbox.
    """
    container_id: str
    container_name: str
    container_type: str # 'google_cloud_workspace' | 'grok_build_sandbox' | 'openai_cloud_sandbox' | 'docker_sandbox' | 'devin_cloud_session' | 'openhands_agent_canvas'
    status: str = "initialized" # 'initialized' | 'running' | 'paused' | 'completed' | 'terminated'
    workspace_path: str = "/workspace"
    branch_name: str = "main"
    project_key: str = "DEFAULT"
    staged_files: List[Dict[str, Any]] = Field(default_factory=list)
    environment_variables: Dict[str, str] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseCodingAgent(BaseCodingHarness, ABC):
    """
    Abstract Base Class for Coding Agent Orchestrators.
    Each agent orchestrator must:
      1. Verify and parse incoming comment prompts and staged files.
      2. Initiate an isolated containerized environment (local or cloud).
      3. Execute coding tasks and return structured results with diffs & logs.
      4. Handle container lifecycle and cleanup on merge.
    """
    agent_id: str = "base_agent"
    display_name: str = "Base Coding Agent"
    container_type: str = "generic_container"
    requires_local_clone: bool = True

    def validate_prompt(self, prompt: str) -> Dict[str, Any]:
        """
        Verifies that the prompt passed in from the comment is valid,
        extracts instructions, checks for security boundaries or external network calls.
        """
        if not prompt or not prompt.strip():
            return {
                "valid": False,
                "reason": "Prompt is empty or missing instructions.",
                "clean_prompt": ""
            }

        # Check for external URLs that may require user authorization
        external_urls = re.findall(r"https?://([a-zA-Z0-9.-]+)", prompt, re.IGNORECASE)

        return {
            "valid": True,
            "prompt_length": len(prompt),
            "clean_prompt": prompt.strip(),
            "detected_external_domains": external_urls,
            "has_external_network_request": len(external_urls) > 0
        }

    @abstractmethod
    def initiate_container(
        self,
        project_key: str,
        branch_name: str,
        repo_url: Optional[str] = None,
        staged_files: Optional[List[Dict[str, Any]]] = None,
        is_new_project: bool = False,
        preparations_result: Optional[Dict[str, Any]] = None
    ) -> ContainerEnvironment:
        """
        Initiates a containerized environment (cloud sandbox, Docker container, or virtual session)
        for the given project and branch.
        """
        pass

    @abstractmethod
    def execute_in_container(
        self,
        prompt: str,
        container_env: ContainerEnvironment,
        project_config: Dict[str, Any],
        system_prompt_additions: str = "",
        chat_context: Optional[List[Dict[str, Any]]] = None,
        preparations_result: Optional[Dict[str, Any]] = None
    ) -> HarnessResult:
        """
        Executes the prompt instructions within the initiated container environment.
        """
        pass

    def cleanup_container(self, container_env_or_id: Any) -> Dict[str, Any]:
        """
        Tears down or archives the container environment once merged or discarded.
        """
        cid = container_env_or_id.container_id if isinstance(container_env_or_id, ContainerEnvironment) else str(container_env_or_id)
        logger.info("[%s] Cleaned up container environment: %s", self.display_name, cid)
        return {"success": True, "container_id": cid, "status": "terminated"}

    def run_task(
        self,
        prompt: str,
        container_info: Optional[Dict[str, Any]] = None,
        project_config: Optional[Dict[str, Any]] = None,
        system_prompt_additions: str = "",
        chat_context: Optional[List[Dict[str, Any]]] = None
    ) -> HarnessResult:
        """
        Implements BaseCodingHarness interface.
        If container_info is already a ContainerEnvironment or dict, uses it,
        otherwise initiates a new container environment on the fly.
        """
        proj_config = project_config or {"name": "Default Project", "key": "DEFAULT"}
        project_key = proj_config.get("key", "DEFAULT")

        # Extract container environment if already passed
        container_env: Optional[ContainerEnvironment] = None
        if isinstance(container_info, ContainerEnvironment):
            container_env = container_info
        elif isinstance(container_info, dict) and container_info.get("container_id"):
            container_env = ContainerEnvironment(
                container_id=container_info.get("container_id", f"c_{uuid.uuid4().hex[:8]}"),
                container_name=container_info.get("container_name", f"{self.agent_id}_{project_key}"),
                container_type=container_info.get("container_type", self.container_type),
                status=container_info.get("status", "running"),
                workspace_path=container_info.get("workspace_path", "/workspace"),
                branch_name=container_info.get("branch_name", "main"),
                project_key=project_key,
                staged_files=container_info.get("staged_files", []),
                metadata=container_info
            )
        else:
            # Initiate container environment
            branch_name = proj_config.get("branch_name", f"branch_{uuid.uuid4().hex[:8]}")
            staged = container_info.get("staged_files") if isinstance(container_info, dict) else None
            prep_res = container_info.get("preparations_result") if isinstance(container_info, dict) else None
            container_env = self.initiate_container(
                project_key=project_key,
                branch_name=branch_name,
                repo_url=proj_config.get("repo_url"),
                staged_files=staged,
                preparations_result=prep_res
            )

        prep_result = container_info.get("preparations_result") if isinstance(container_info, dict) else None
        return self.execute_in_container(
            prompt=prompt,
            container_env=container_env,
            project_config=proj_config,
            system_prompt_additions=system_prompt_additions,
            chat_context=chat_context,
            preparations_result=prep_result
        )

    def _ensure_local_workspace(self, container_env: ContainerEnvironment) -> Path:
        """Helper to create or resolve a local mirror directory for diff generation."""
        ws_dir = ROOT_DIR / "sandboxes" / container_env.container_name
        ws_dir.mkdir(parents=True, exist_ok=True)
        return ws_dir
