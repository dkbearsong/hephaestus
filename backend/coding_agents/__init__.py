"""
Hephaestus Coding Agents Module
Integrates 7 containerized coding agent platforms:
  - Google Jules (Google Cloud Workspace)
  - Grok Build (xAI Sandbox)
  - OpenAI Codex Cloud (Cloud Sandbox)
  - Docker Sandbox (Claude Code / OpenAI Codex)
  - Devin AI (Cognition Session Sandbox)
  - OpenHands with Agent Canvas (Visual Agent Canvas)
  - Cursor (Cursor Cloud Agents & Dev Containers)
"""

from backend.coding_agents.base import BaseCodingAgent, ContainerEnvironment
from backend.coding_agents.google_jules import GoogleJulesOrchestrator
from backend.coding_agents.grok_build import GrokBuildOrchestrator
from backend.coding_agents.openai_codex_cloud import OpenAICodexCloudOrchestrator
from backend.coding_agents.docker_sandbox_claude_codex import DockerSandboxClaudeCodexOrchestrator
from backend.coding_agents.devin_ai import DevinAIOrchestrator
from backend.coding_agents.openhands_canvas import OpenHandsAgentCanvasOrchestrator
from backend.coding_agents.cursor_agent import CursorAgentOrchestrator
from backend.coding_agents.orchestrator import (
    CodingAgentOrchestrator,
    coding_agent_orchestrator
)

__all__ = [
    "BaseCodingAgent",
    "ContainerEnvironment",
    "GoogleJulesOrchestrator",
    "GrokBuildOrchestrator",
    "OpenAICodexCloudOrchestrator",
    "DockerSandboxClaudeCodexOrchestrator",
    "DevinAIOrchestrator",
    "OpenHandsAgentCanvasOrchestrator",
    "CursorAgentOrchestrator",
    "CodingAgentOrchestrator",
    "coding_agent_orchestrator"
]
