from pathlib import Path
from typing import Dict, List, Optional, Union, Any
import os
import yaml
import sys
from pydantic import BaseModel, Field, ConfigDict


class ServerConfig(BaseModel):
    """
    Standard stdio MCP server configuration.
    """
    command: str = Field(..., description="Executable binary or command to run")
    args: List[str] = Field(default_factory=list, description="Command line arguments")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")
    cwd: Optional[str] = Field(None, description="Optional working directory for server process")


class UserPreferences(BaseModel):
    """
    Root user preferences model supporting MCP server configurations and extensible fields.
    """
    model_config = ConfigDict(extra="allow")

    mcp_servers: Dict[str, ServerConfig] = Field(
        default_factory=dict,
        description="Configured external stdio MCP servers"
    )


def get_default_server_config(workspace_dir: Path) -> ServerConfig:
    """
    Generates the built-in MCP server configuration scoped to the given workspace directory.
    """
    root_dir = Path(__file__).resolve().parent.parent
    return ServerConfig(
        command=sys.executable,
        args=["-m", "services.builtin_tools_server", "--workspace", str(workspace_dir.resolve())],
        env={"PYTHONPATH": str(root_dir)},
        cwd=str(workspace_dir.resolve())
    )


def find_preferences_file(custom_path: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """
    Locates user-preferences file from explicit path or common repository root names.
    """
    if custom_path:
        p = Path(custom_path)
        if p.exists():
            return p.resolve()
        return None

    root_dir = Path(__file__).resolve().parent.parent
    p = root_dir / "user_preferences.yaml"
    if p.exists():
        return p.resolve()

    return None


def load_user_preferences(prefs_path: Optional[Union[str, Path]] = None) -> UserPreferences:
    """
    Loads UserPreferences from yaml file. If not found or invalid, returns empty UserPreferences.
    """
    file_path = find_preferences_file(prefs_path)
    if not file_path or not file_path.exists():
        return UserPreferences()

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                return UserPreferences()
            return UserPreferences.model_validate(data)
    except Exception:
        return UserPreferences()


def load_and_merge_servers(
    prefs_path: Optional[Union[str, Path]],
    workspace_dir: Path
) -> Dict[str, ServerConfig]:
    """
    Loads user preferences and safely merges user-defined external servers with internal default servers.
    The internal 'builtin' server is always provided and guaranteed to be present unless overridden.
    """
    merged: Dict[str, ServerConfig] = {
        "builtin": get_default_server_config(workspace_dir)
    }

    user_prefs = load_user_preferences(prefs_path)
    if user_prefs.mcp_servers:
        for name, cfg in user_prefs.mcp_servers.items():
            merged[name] = cfg

    return merged
