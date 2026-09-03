from backend.harness.base import BaseCodingHarness, HarnessResult
from backend.harness.langgraph_harness import LangGraphHarness
from backend.harness.registry import HarnessRegistry, harness_registry
from backend.coding_agents.google_jules import GoogleJulesOrchestrator
from backend.coding_agents.grok_build import GrokBuildOrchestrator
from backend.coding_agents.openai_codex_cloud import OpenAICodexCloudOrchestrator
from backend.coding_agents.docker_sandbox_claude_codex import DockerSandboxClaudeCodexOrchestrator
from backend.coding_agents.devin_ai import DevinAIOrchestrator
from backend.coding_agents.openhands_canvas import OpenHandsAgentCanvasOrchestrator
from backend.coding_agents.cursor_agent import CursorAgentOrchestrator

def get_active_harness() -> BaseCodingHarness:
    """Returns the currently active coding harness via the registry."""
    return harness_registry.get_active_harness()

def set_active_harness(harness):
    """Sets the active coding harness instance or registered name."""
    harness_registry.set_active_harness(harness)

def reset_active_harness():
    """Resets the active harness to default."""
    harness_registry.reset_active_harness()

__all__ = [
    "BaseCodingHarness",
    "HarnessResult",
    "LangGraphHarness",
    "GoogleJulesOrchestrator",
    "GrokBuildOrchestrator",
    "OpenAICodexCloudOrchestrator",
    "DockerSandboxClaudeCodexOrchestrator",
    "DevinAIOrchestrator",
    "OpenHandsAgentCanvasOrchestrator",
    "CursorAgentOrchestrator",
    "HarnessRegistry",
    "harness_registry",
    "get_active_harness",
    "set_active_harness",
    "reset_active_harness",
]
