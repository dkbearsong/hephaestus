"""
Registry for Coding Agent Harnesses and Adapters
Supports all 7 containerized coding agent platforms, LangGraph state machine,
and test harnesses (stubs, mocks, virtualizers).
"""

import logging
from typing import Dict, Any, Union, Optional
from backend.harness.base import BaseCodingHarness
from backend.config import preferences

logger = logging.getLogger("hephaestus.harness_registry")

class HarnessRegistry:
    """
    Registry for AI coding harnesses, enabling plug-and-play architecture
    for production coding agent platforms, LangGraph agent, and test harnesses.
    """

    def __init__(self):
        self._registry: Dict[str, Any] = {}
        self._active_override: Optional[BaseCodingHarness] = None
        self._init_defaults()

    def _init_defaults(self):
        # Import coding agent orchestrators
        from backend.coding_agents.google_jules import GoogleJulesOrchestrator
        from backend.coding_agents.grok_build import GrokBuildOrchestrator
        from backend.coding_agents.openai_codex_cloud import OpenAICodexCloudOrchestrator
        from backend.coding_agents.docker_sandbox_claude_codex import DockerSandboxClaudeCodexOrchestrator
        from backend.coding_agents.devin_ai import DevinAIOrchestrator
        from backend.coding_agents.openhands_canvas import OpenHandsAgentCanvasOrchestrator
        from backend.coding_agents.cursor_agent import CursorAgentOrchestrator
        from backend.harness.langgraph_harness import LangGraphHarness

        # Register coding agent platforms
        self._registry["google_jules"] = GoogleJulesOrchestrator
        self._registry["grok_build"] = GrokBuildOrchestrator
        self._registry["openai_codex_cloud"] = OpenAICodexCloudOrchestrator
        self._registry["docker_sandbox_claude_codex"] = DockerSandboxClaudeCodexOrchestrator
        self._registry["devin_ai"] = DevinAIOrchestrator
        self._registry["openhands_canvas"] = OpenHandsAgentCanvasOrchestrator
        self._registry["cursor_agent"] = CursorAgentOrchestrator

        # Register LangGraph agent
        self._registry["langgraph_agent"] = LangGraphHarness

        # Friendly aliases & legacy compatibility
        self._registry["jules"] = GoogleJulesOrchestrator
        self._registry["grok"] = GrokBuildOrchestrator
        self._registry["codex"] = OpenAICodexCloudOrchestrator
        self._registry["openai_codex"] = OpenAICodexCloudOrchestrator
        self._registry["docker_sandbox"] = DockerSandboxClaudeCodexOrchestrator
        self._registry["docker_claude_codex"] = DockerSandboxClaudeCodexOrchestrator
        self._registry["claude_code"] = DockerSandboxClaudeCodexOrchestrator
        self._registry["devin"] = DevinAIOrchestrator
        self._registry["openhands"] = OpenHandsAgentCanvasOrchestrator
        self._registry["openhands_agent_canvas"] = OpenHandsAgentCanvasOrchestrator
        self._registry["cursor"] = CursorAgentOrchestrator
        self._registry["cursor_cloud"] = CursorAgentOrchestrator
        self._registry["cursor_dev_container"] = CursorAgentOrchestrator
        # Legacy fallback
        self._registry["antigravity_daemon"] = GoogleJulesOrchestrator

    def register_harness(self, name: str, harness_cls_or_instance: Union[type, BaseCodingHarness]):
        """Register a new harness (class or instance) under a key."""
        key = name.lower()
        self._registry[key] = harness_cls_or_instance
        logger.info("[HarnessRegistry] Registered harness: %s", key)

    def set_active_harness(self, harness: Union[str, BaseCodingHarness]):
        """
        Sets the active harness. Can be an instantiated BaseCodingHarness
        (e.g., a test stub or mock) or a string key matching a registered harness.
        """
        if isinstance(harness, BaseCodingHarness):
            self._active_override = harness
            logger.info("[HarnessRegistry] Active harness overridden with instance: %s", type(harness).__name__)
        elif isinstance(harness, str):
            key = harness.lower()
            if key not in self._registry:
                raise KeyError(f"Harness '{harness}' not found in registry. Registered: {list(self._registry.keys())}")
            target = self._registry[key]
            self._active_override = target() if isinstance(target, type) else target
            logger.info("[HarnessRegistry] Active harness set to registered key: %s", key)
        else:
            raise TypeError("Expected BaseCodingHarness instance or string name")

    def reset_active_harness(self):
        """Resets any active override back to the configuration preference."""
        self._active_override = None
        logger.info("[HarnessRegistry] Reset active harness to preferences default.")

    def get_active_harness(self) -> BaseCodingHarness:
        """Returns the currently active coding harness."""
        if self._active_override is not None:
            return self._active_override

        # Fallback to configured preference
        active_key = preferences.harness.active.lower()
        if active_key in self._registry:
            target = self._registry[active_key]
            return target() if isinstance(target, type) else target

        # Default fallback to Google Jules
        from backend.coding_agents.google_jules import GoogleJulesOrchestrator
        return GoogleJulesOrchestrator()

# Singleton instance
harness_registry = HarnessRegistry()
