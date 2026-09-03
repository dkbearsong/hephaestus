"""
Central Coding Agent Orchestrator
Routes tasks after the Preparations AI Agent to the selected Coding Agent platform
(Google Jules, Grok Build, OpenAI Codex Cloud, Docker Sandbox Claude/Codex, Devin AI, OpenHands Agent Canvas, Cursor)
and manages containerized environment lifecycles.
"""

import logging
from typing import Dict, Any, List, Optional, Union
from backend.config import preferences
from backend.coding_agents.base import BaseCodingAgent, ContainerEnvironment
from backend.coding_agents.google_jules import GoogleJulesOrchestrator
from backend.coding_agents.grok_build import GrokBuildOrchestrator
from backend.coding_agents.openai_codex_cloud import OpenAICodexCloudOrchestrator
from backend.coding_agents.docker_sandbox_claude_codex import DockerSandboxClaudeCodexOrchestrator
from backend.coding_agents.devin_ai import DevinAIOrchestrator
from backend.coding_agents.openhands_canvas import OpenHandsAgentCanvasOrchestrator
from backend.coding_agents.cursor_agent import CursorAgentOrchestrator
from backend.harness.base import HarnessResult

logger = logging.getLogger("hephaestus.coding_agents.orchestrator")

class CodingAgentOrchestrator:
    """
    Master orchestrator managing all containerized coding agent integrations.
    """

    def __init__(self):
        self._agents: Dict[str, BaseCodingAgent] = {}
        self._aliases: Dict[str, str] = {}
        self._active_override: Optional[Union[str, BaseCodingAgent]] = None
        self._active_containers: Dict[str, ContainerEnvironment] = {}
        self._init_agents()

    def _init_agents(self):
        # Register standard agent platforms
        self.register_agent(GoogleJulesOrchestrator())
        self.register_agent(GrokBuildOrchestrator())
        self.register_agent(OpenAICodexCloudOrchestrator())
        self.register_agent(DockerSandboxClaudeCodexOrchestrator(engine="claude_code"))
        self.register_agent(DevinAIOrchestrator())
        self.register_agent(OpenHandsAgentCanvasOrchestrator())
        self.register_agent(CursorAgentOrchestrator())

        # Register friendly aliases
        self._aliases.update({
            "jules": "google_jules",
            "google": "google_jules",
            "google_jules_agent": "google_jules",
            "grok": "grok_build",
            "xai": "grok_build",
            "grok_agent": "grok_build",
            "codex": "openai_codex_cloud",
            "openai_codex": "openai_codex_cloud",
            "codex_cloud": "openai_codex_cloud",
            "docker_sandbox": "docker_sandbox_claude_codex",
            "docker_claude_codex": "docker_sandbox_claude_codex",
            "claude_code": "docker_sandbox_claude_codex",
            "devin": "devin_ai",
            "cognition": "devin_ai",
            "cognition_devin": "devin_ai",
            "openhands": "openhands_canvas",
            "openhands_agent_canvas": "openhands_canvas",
            "all_hands": "openhands_canvas",
            "cursor": "cursor_agent",
            "cursor_cloud": "cursor_agent",
            "cursor_cloud_agent": "cursor_agent",
            "cursor_dev_container": "cursor_agent",
            "cursor_devcontainer": "cursor_agent"
        })

    def register_agent(self, agent: BaseCodingAgent):
        """Registers a coding agent instance."""
        self._agents[agent.agent_id.lower()] = agent
        logger.info("[CodingAgentOrchestrator] Registered agent: %s (%s)", agent.agent_id, agent.display_name)

    def list_supported_agents(self) -> List[Dict[str, Any]]:
        """Returns metadata for all available coding agent orchestrators."""
        result = []
        for key, agent in self._agents.items():
            result.append({
                "agent_id": agent.agent_id,
                "display_name": agent.display_name,
                "container_type": agent.container_type
            })
        return result

    def get_agent(self, agent_name: Optional[str] = None) -> BaseCodingAgent:
        """
        Resolves the active or requested coding agent orchestrator.
        """
        if self._active_override and isinstance(self._active_override, BaseCodingAgent):
            return self._active_override

        target_name = agent_name or (self._active_override if isinstance(self._active_override, str) else None)
        if not target_name:
            target_name = getattr(preferences.harness, "active", "google_jules")

        key = str(target_name).lower().strip()
        resolved_key = self._aliases.get(key, key)

        if resolved_key in self._agents:
            agent = self._agents[resolved_key]
            # Configure cursor mode if specific alias was passed
            if resolved_key == "cursor_agent" and isinstance(agent, CursorAgentOrchestrator):
                if "dev_container" in key or "devcontainer" in key:
                    agent.mode = "cursor_dev_container"
                elif "cloud" in key:
                    agent.mode = "cursor_cloud"
            return agent

        # Fallback to Google Jules if unknown
        logger.warning("[CodingAgentOrchestrator] Unknown agent '%s', falling back to google_jules.", key)
        return self._agents.get("google_jules", next(iter(self._agents.values())))

    def set_active_agent(self, agent: Union[str, BaseCodingAgent]):
        """Overrides the active coding agent."""
        self._active_override = agent
        logger.info("[CodingAgentOrchestrator] Active coding agent overridden: %s", agent)

    def reset_active_agent(self):
        """Resets active override back to system preferences default."""
        self._active_override = None
        logger.info("[CodingAgentOrchestrator] Active coding agent reset to preferences default.")

    def execute_workflow(
        self,
        prompt: str,
        project_key: str,
        branch_name: str,
        repo_url: Optional[str] = None,
        staged_files: Optional[List[Dict[str, Any]]] = None,
        is_new_project: bool = False,
        system_prompt_additions: str = "",
        chat_context: Optional[List[Dict[str, Any]]] = None,
        preparations_result: Optional[Dict[str, Any]] = None,
        target_agent: Optional[str] = None
    ) -> HarnessResult:
        """
        Full execution pipeline:
          1. Resolves agent orchestrator.
          2. Validates prompt instructions.
          3. Initiates containerized environment.
          4. Executes task in container and synthesizes diff/logs.
        """
        agent = self.get_agent(target_agent)
        logger.info("[CodingAgentOrchestrator] Dispatching task to agent: %s for %s (%s)",
                    agent.display_name, project_key, branch_name)

        # Step 1: Validate prompt
        val = agent.validate_prompt(prompt)
        if not val["valid"]:
            return HarnessResult(
                status="failed",
                summary_changes="Prompt validation failed.",
                what_was_wrong="Missing or invalid prompt instructions in comment.",
                full_log=f"Validation error: {val.get('reason')}"
            )

        # Step 2: Initiate containerized environment
        container_env = agent.initiate_container(
            project_key=project_key,
            branch_name=branch_name,
            repo_url=repo_url,
            staged_files=staged_files,
            is_new_project=is_new_project,
            preparations_result=preparations_result
        )
        container_key = f"{project_key}_{branch_name}"
        self._active_containers[container_key] = container_env

        # Step 3: Execute task within the initiated container
        result = agent.execute_in_container(
            prompt=prompt,
            container_env=container_env,
            project_config={"key": project_key, "branch_name": branch_name, "repo_url": repo_url},
            system_prompt_additions=system_prompt_additions,
            chat_context=chat_context,
            preparations_result=preparations_result
        )

        return result

    def cleanup_container(self, project_key: str, branch_name: str, agent_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Cleans up container resources when branch is merged.
        """
        container_key = f"{project_key}_{branch_name}"
        container_env = self._active_containers.pop(container_key, None)
        agent = self.get_agent(agent_name)

        if container_env:
            return agent.cleanup_container(container_env)
        return agent.cleanup_container(container_key)

# Global singleton instance
coding_agent_orchestrator = CodingAgentOrchestrator()
