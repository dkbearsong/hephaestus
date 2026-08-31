import os
import json
import inspect
import asyncio
import importlib.util
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable
from backend.config import preferences, ROOT_DIR

logger = logging.getLogger("hephaestus.mcp")

class McpToolLoader:
    def __init__(self):
        self.tools_dir = ROOT_DIR / getattr(preferences.mcp_tools, "tools_directory", "mcp_tools")
        self.enabled_tools = getattr(preferences.mcp_tools, "enabled", ["datetime_tool", "postgres_inspector", "test_runner"])
        self._loaded_modules: Dict[str, Any] = {}
        self._tool_function_map: Dict[str, Tuple[str, Callable]] = {} # func_name -> (module_name, func)

    def discover_all_available_tools(self) -> List[str]:
        """
        Discovers all available tool modules in the mcp_tools directory.
        Returns list of tool module names (without .py extension).
        """
        if not self.tools_dir.exists():
            return []
        available = []
        for file in sorted(self.tools_dir.glob("*.py")):
            if not file.name.startswith("__") and not file.name.startswith("."):
                available.append(file.stem)
        return available

    def get_available_tool_names(self) -> List[str]:
        """Returns list of discovered tool module names."""
        return self.discover_all_available_tools()

    def load_module(self, tool_name: str) -> Optional[Any]:
        """Loads a single tool module by name."""
        if tool_name in self._loaded_modules:
            return self._loaded_modules[tool_name]

        tool_file = self.tools_dir / f"{tool_name}.py"
        if not tool_file.exists():
            logger.warning("MCP tool file '%s' does not exist.", tool_file)
            return None

        try:
            spec = importlib.util.spec_from_file_location(tool_name, tool_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self._loaded_modules[tool_name] = module
                self._register_module_functions(tool_name, module)
                logger.info("Successfully loaded MCP tool module: %s", tool_name)
                return module
        except Exception as e:
            logger.error("Failed to load MCP tool %s: %s", tool_name, e)
            return None

    def _register_module_functions(self, module_name: str, module: Any):
        """Maps callable tool functions in the module for direct execution and schema generation."""
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            if not name.startswith("_") and name != "get_connection":
                self._tool_function_map[name] = (module_name, obj)

    def load_active_tools(self) -> Dict[str, Any]:
        """
        Loads enabled MCP tools from the user-specified mcp_tools folder.
        """
        loaded = {}
        if not self.tools_dir.exists():
            logger.warning("MCP tools directory %s does not exist.", self.tools_dir)
            return loaded

        # Re-fetch enabled list from preferences
        enabled = getattr(preferences.mcp_tools, "enabled", self.enabled_tools)
        for tool_name in enabled:
            mod = self.load_module(tool_name)
            if mod:
                loaded[tool_name] = mod

        return loaded

    def load_all_tools(self) -> Dict[str, Any]:
        """Loads all available MCP tools in the tools directory."""
        all_names = self.discover_all_available_tools()
        loaded = {}
        for name in all_names:
            mod = self.load_module(name)
            if mod:
                loaded[name] = mod
        return loaded

    def get_tool_schemas(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """
        Generates OpenAI-compatible tool definitions (schemas) for loaded MCP tools.
        Format:
        [
            {
                "type": "function",
                "function": {
                    "name": "...",
                    "description": "...",
                    "parameters": {...}
                }
            }
        ]
        """
        if enabled_only:
            self.load_active_tools()
        else:
            self.load_all_tools()

        schemas = []
        enabled_set = set(getattr(preferences.mcp_tools, "enabled", self.enabled_tools)) if enabled_only else None

        for func_name, (mod_name, func) in self._tool_function_map.items():
            if enabled_set is not None and mod_name not in enabled_set:
                continue

            doc = inspect.getdoc(func) or f"Execute {func_name} in {mod_name}"
            sig = inspect.signature(func)

            properties = {}
            required = []

            for param_name, param in sig.parameters.items():
                if param_name in ("self", "cls"):
                    continue

                param_type = "string"
                if param.annotation == int:
                    param_type = "integer"
                elif param.annotation == float:
                    param_type = "number"
                elif param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation in (list, List):
                    param_type = "array"
                elif param.annotation in (dict, Dict):
                    param_type = "object"

                prop_dict: Dict[str, Any] = {"type": param_type}
                if param.default is not inspect.Parameter.empty:
                    prop_dict["default"] = param.default
                else:
                    required.append(param_name)

                properties[param_name] = prop_dict

            schema = {
                "type": "function",
                "function": {
                    "name": func_name,
                    "description": doc.strip(),
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required
                    }
                }
            }
            schemas.append(schema)

        return schemas

    def execute_tool(self, function_name: str, arguments: Optional[Dict[str, Any]] = None, tool_name: Optional[str] = None) -> Any:
        """
        Executes an MCP tool function by name.
        Handles FastMCP call_tool and synchronous/asynchronous Python functions.
        """
        arguments = arguments or {}
        self.load_active_tools()

        if function_name not in self._tool_function_map:
            # Try finding in all tools
            self.load_all_tools()

        if function_name not in self._tool_function_map:
            raise ValueError(f"MCP Tool function '{function_name}' not found. Available: {list(self._tool_function_map.keys())}")

        mod_name, func = self._tool_function_map[function_name]
        module = self._loaded_modules.get(mod_name)

        # Check if module has FastMCP instance with call_tool
        mcp_obj = getattr(module, "mcp", None)
        if mcp_obj and hasattr(mcp_obj, "call_tool"):
            try:
                # FastMCP call_tool can be async
                loop = None
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                if loop.is_running():
                    # If running inside async loop, run directly as task or call underlying func
                    if asyncio.iscoroutinefunction(func):
                        import concurrent.futures
                        # Use thread pool to avoid loop collision
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(lambda: asyncio.run(func(**arguments)))
                            return future.result()
                    else:
                        return func(**arguments)
                else:
                    call_coro = mcp_obj.call_tool(function_name, arguments)
                    res = loop.run_until_complete(call_coro)
                    if hasattr(res, "structured_content") and res.structured_content:
                        return res.structured_content
                    if hasattr(res, "content") and res.content:
                        # Extract text
                        texts = [getattr(c, "text", str(c)) for c in res.content]
                        return "\n".join(texts)
                    return str(res)
            except Exception as e:
                logger.warning("FastMCP call_tool failed (%s), falling back to direct function call.", e)

        # Fallback direct function execution
        if inspect.iscoroutinefunction(func):
            return asyncio.run(func(**arguments))
        return func(**arguments)

    def save_tool_catalog(self, output_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Saves a catalog of all discovered MCP tools and schemas to a JSON file.
        Defaults to {tools_dir}/tool_catalog.json.
        """
        available = self.discover_all_available_tools()
        schemas = self.get_tool_schemas(enabled_only=False)

        catalog = {
            "total_tools": len(available),
            "tool_modules": available,
            "enabled_tools": getattr(preferences.mcp_tools, "enabled", self.enabled_tools),
            "schemas": schemas
        }

        target_file = output_path or (self.tools_dir / "tool_catalog.json")
        target_file.parent.mkdir(parents=True, exist_ok=True)
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2)

        logger.info("Saved MCP tool catalog to %s", target_file)
        return catalog

mcp_loader = McpToolLoader()
