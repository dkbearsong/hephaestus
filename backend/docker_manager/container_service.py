"""
DEPRECATED / DISABLED MODULE: Docker Container Service
This module has been disabled and archived in old_code/container_service.py.
Containerized workspace management is now handled directly by the Coding Agent Orchestrator
(backend/coding_agents/) across Google Jules, Grok Build, OpenAI Codex Cloud,
Docker Sandbox (Claude Code/Codex), Devin AI, and OpenHands Agent Canvas.
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("hephaestus.docker_manager.disabled")

class DisabledDockerContainerManager:
    """
    Disabled placeholder for the legacy DockerContainerManager.
    All operations are disabled in favor of backend.coding_agents.
    """
    def __init__(self):
        logger.info("[DockerManager] Legacy Docker container manager is disabled. Use backend.coding_agents.")

    def ensure_branch_container(
        self,
        project_key: str,
        branch_name: str,
        repo_url: Optional[str] = None,
        base_image: Optional[str] = None,
        staged_files: Optional[List[Dict[str, Any]]] = None,
        is_new_project: bool = False
    ) -> Dict[str, Any]:
        logger.warning("[DockerManager] ensure_branch_container called on disabled legacy manager.")
        return {
            "success": True,
            "container_id": f"delegated_{project_key}_{branch_name}",
            "container_name": f"delegated_{project_key}_{branch_name}",
            "status": "delegated_to_coding_agent",
            "checkpoint_tag": f"delegated:{project_key}",
            "workspace_path": f"/workspace/{branch_name}"
        }

    def spin_down_and_checkpoint(self, container_name: str, checkpoint_tag: str) -> Dict[str, Any]:
        logger.info("[DockerManager] Legacy checkpoint skipped (managed by coding agent platform).")
        return {"success": True, "status": "delegated"}

    def delete_on_merge(self, project_key: str, branch_name: str) -> Dict[str, Any]:
        logger.info("[DockerManager] Legacy delete on merge skipped (managed by coding agent platform).")
        return {"success": True, "deleted": True}

docker_manager = DisabledDockerContainerManager()
