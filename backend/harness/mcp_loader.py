import importlib.util
import logging
from pathlib import Path
from typing import Dict, Any, List
from backend.config import preferences, ROOT_DIR

logger = logging.getLogger("hephaestus.mcp")

class McpToolLoader:
    def __init__(self):
        self.tools_dir = ROOT_DIR / preferences.mcp_tools.tools_directory
        self.enabled_tools = preferences.mcp_tools.enabled

    def load_active_tools(self) -> Dict[str, Any]:
        """
        Loads enabled MCP tools from the user-specified mcp_tools folder.
        """
        loaded = {}
        if not self.tools_dir.exists():
            logger.warning("MCP tools directory %s does not exist.", self.tools_dir)
            return loaded

        for tool_name in self.enabled_tools:
            tool_file = self.tools_dir / f"{tool_name}.py"
            if tool_file.exists():
                try:
                    spec = importlib.util.spec_from_file_location(tool_name, tool_file)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        loaded[tool_name] = module
                        logger.info("Successfully loaded active MCP tool: %s", tool_name)
                except Exception as e:
                    logger.error("Failed to load MCP tool %s: %s", tool_name, e)
            else:
                logger.warning("MCP tool '%s' declared in user_preferences.yaml but %s not found.", tool_name, tool_file)

        return loaded

mcp_loader = McpToolLoader()
