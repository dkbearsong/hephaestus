import os
import sys
import shutil
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from services.config import ServerConfig, load_and_merge_servers

logger = logging.getLogger("hephaestus.mcp")


def extract_tool_result_text(result: Any) -> str:
    """
    Extracts a plain-text representation from an MCP CallToolResult or similar output.
    """
    if result is None:
        return ""

    if hasattr(result, "content") and result.content:
        texts = []
        for item in result.content:
            if hasattr(item, "text"):
                texts.append(item.text)
            elif isinstance(item, dict) and "text" in item:
                texts.append(item["text"])
            else:
                texts.append(str(item))
        return "\n".join(texts)

    if hasattr(result, "structuredContent") and result.structuredContent:
        return json.dumps(result.structuredContent)

    return str(result)


class MCPManager:
    """
    Asynchronous MCP Client Manager.
    Manages dynamic lifecycle for built-in and user-configured MCP servers,
    aggregates tool definitions, and dispatches calls to the appropriate session.
    """

    def __init__(
        self,
        server_configs: Dict[str, ServerConfig],
        workspace_dir: Union[str, Path]
    ):
        self.server_configs = server_configs
        self.workspace_dir = Path(workspace_dir).resolve()
        self._exit_stack: Optional[AsyncExitStack] = None
        self._sessions: Dict[str, ClientSession] = {}
        self._tools: Dict[str, Tuple[ClientSession, Any]] = {}
        self._files_modified: List[str] = []
        self._last_completion: Optional[Dict[str, Any]] = None

    @classmethod
    def from_preferences(
        cls,
        prefs_path: Optional[Union[str, Path]],
        workspace_dir: Union[str, Path]
    ) -> "MCPManager":
        """
        Creates an MCPManager from user preferences and internal default servers.
        """
        w_dir = Path(workspace_dir).resolve()
        merged_configs = load_and_merge_servers(prefs_path, w_dir)
        return cls(server_configs=merged_configs, workspace_dir=w_dir)

    async def __aenter__(self) -> "MCPManager":
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()

        for server_name, cfg in self.server_configs.items():
            try:
                merged_env = os.environ.copy()
                if cfg.env:
                    merged_env.update(cfg.env)

                # Ensure PYTHONPATH contains project root
                project_root = str(Path(__file__).resolve().parent.parent)
                if "PYTHONPATH" in merged_env:
                    merged_env["PYTHONPATH"] = f"{project_root}:{merged_env['PYTHONPATH']}"
                else:
                    merged_env["PYTHONPATH"] = project_root

                # Resolve executable binary safely
                cmd = cfg.command
                if cmd in ("python", "python3"):
                    cmd = shutil.which(cmd) or sys.executable
                else:
                    which_cmd = shutil.which(cmd)
                    if which_cmd:
                        cmd = which_cmd

                server_params = StdioServerParameters(
                    command=cmd,
                    args=cfg.args,
                    env=merged_env,
                    cwd=cfg.cwd or str(self.workspace_dir)
                )

                read_stream, write_stream = await self._exit_stack.enter_async_context(
                    stdio_client(server_params)
                )
                session = await self._exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                await session.initialize()
                self._sessions[server_name] = session

                # Aggregate tools
                tools_result = await session.list_tools()
                for tool in tools_result.tools:
                    self._tools[tool.name] = (session, tool)

                logger.info(
                    "Connected to MCP server '%s' (%d tools registered)",
                    server_name,
                    len(tools_result.tools)
                )
            except Exception as e:
                # Fault Tolerance:
                # If an external MCP server from user_preferences.yaml fails to start,
                # log an error and continue with the built-in tools rather than crashing the pipeline.
                if server_name == "builtin":
                    logger.error("Failed to start critical built-in MCP server '%s': %s", server_name, e)
                    raise
                else:
                    logger.error(
                        "External MCP server '%s' failed to start: %s. Continuing with active servers.",
                        server_name,
                        e
                    )

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._exit_stack:
            await self._exit_stack.aclose()
            self._exit_stack = None
        self._sessions.clear()
        self._tools.clear()

    async def get_available_tools(self) -> List[Any]:
        """
        Returns list of all aggregated MCP tool definitions.
        """
        return [tool for (_, tool) in self._tools.values()]

    def get_tool(self, tool_name: str) -> Optional[Any]:
        """
        Returns original tool definition by name.
        """
        if tool_name in self._tools:
            return self._tools[tool_name][1]
        return None

    def get_registered_tool_names(self) -> List[str]:
        """
        Returns names of all currently registered tools.
        """
        return list(self._tools.keys())

    async def call_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Dispatches a tool call to the matching MCP server session.
        Emits tool call logs and tracks file modifications.
        """
        args = arguments or {}
        logger.info("[MCP] Invoking tool '%s' with arguments: %s", tool_name, args)

        if tool_name not in self._tools:
            err_msg = f"MCP tool '{tool_name}' not found. Available: {list(self._tools.keys())}"
            logger.error("[MCP] Tool invocation failed: %s", err_msg)
            raise ValueError(err_msg)

        session, _ = self._tools[tool_name]

        try:
            result = await session.call_tool(tool_name, args)
            is_error = getattr(result, "isError", False)
            if is_error:
                logger.warning("[MCP] Tool '%s' executed with error status: %s", tool_name, result)
            else:
                logger.info("[MCP] Tool '%s' executed successfully", tool_name)

            # Track workspace file modifications
            self._track_modifications(tool_name, args, result)

            return result
        except Exception as e:
            logger.error("[MCP] Execution error calling tool '%s': %s", tool_name, e)
            raise

    def _track_modifications(self, tool_name: str, args: Dict[str, Any], result: Any):
        """
        Tracks modified files and completion payloads.
        """
        if tool_name == "write_file" and "path" in args:
            p = str(args["path"])
            if p not in self._files_modified:
                self._files_modified.append(p)

        elif tool_name == "move_file":
            dest = str(args.get("destination", ""))
            src = str(args.get("source", ""))
            if dest and dest not in self._files_modified:
                self._files_modified.append(dest)
            elif src and src not in self._files_modified:
                self._files_modified.append(src)

        elif tool_name == "delete_file" and "path" in args:
            p = str(args["path"])
            if p not in self._files_modified:
                self._files_modified.append(p)

        elif tool_name == "complete_preparation":
            # Extract structured completion
            if hasattr(result, "structuredContent") and isinstance(result.structuredContent, dict):
                self._last_completion = result.structuredContent
            elif hasattr(result, "content") and result.content:
                text = extract_tool_result_text(result)
                try:
                    self._last_completion = json.loads(text)
                except Exception:
                    self._last_completion = {"raw": text}
            else:
                self._last_completion = dict(args)

    @property
    def files_modified(self) -> List[str]:
        return list(self._files_modified)

    @property
    def last_completion(self) -> Optional[Dict[str, Any]]:
        return self._last_completion
