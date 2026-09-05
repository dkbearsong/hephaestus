import os
import sys
import shutil
import subprocess
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("hephaestus.mcp.builtin")


def resolve_safe_path(base_dir: Path, user_path: str) -> Path:
    """
    Safely resolves a path relative to base_dir, guarding strictly against path traversal.
    Raises PermissionError if the target path resolves outside base_dir.
    """
    p = Path(user_path)
    base_resolved = base_dir.resolve()

    if p.is_absolute():
        resolved = p.resolve()
    else:
        resolved = (base_dir / p).resolve()

    try:
        resolved.relative_to(base_resolved)
    except ValueError:
        raise PermissionError(
            f"Access denied: Path '{user_path}' resolves to '{resolved}', "
            f"which is outside the allowed working directory '{base_resolved}'."
        )

    return resolved


def create_builtin_mcp_server(workspace_dir: Path) -> FastMCP:
    """
    Creates and configures a FastMCP server exposing built-in workspace tools
    scoped and sandboxed to workspace_dir.
    """
    workspace = workspace_dir.resolve()
    mcp = FastMCP("hephaestus-builtin")

    @mcp.tool()
    def list_directory(path: str = ".") -> List[Dict[str, Any]]:
        """
        Lists files and subdirectories in the target directory relative to workspace root.
        """
        target = resolve_safe_path(workspace, path)
        if not target.exists():
            raise FileNotFoundError(f"Directory not found: {path}")
        if not target.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {path}")

        results = []
        for entry in sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.name in (".git", "__pycache__", ".venv", "node_modules"):
                continue
            rel_path = str(entry.relative_to(workspace))
            results.append({
                "name": entry.name,
                "path": rel_path,
                "is_dir": entry.is_dir(),
                "size_bytes": entry.stat().st_size if entry.is_file() else None
            })
        return results

    @mcp.tool()
    def read_file(path: str) -> str:
        """
        Reads target config or source file content within the workspace.
        """
        target = resolve_safe_path(workspace, path)
        if not target.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not target.is_file():
            raise IsADirectoryError(f"Path is a directory, not a file: {path}")

        return target.read_text(encoding="utf-8", errors="replace")

    @mcp.tool()
    def write_file(path: str, content: str) -> str:
        """
        Creates or updates configuration and source files (e.g. .env, package configs).
        Enforces sandboxing inside the workspace directory.
        """
        target = resolve_safe_path(workspace, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        rel_path = str(target.relative_to(workspace))
        return f"Successfully wrote {len(content)} characters to {rel_path}"

    @mcp.tool()
    def move_file(source: str, destination: str) -> str:
        """
        Relocates files (e.g. from .harness_inbox/ or staged_files/ to destination).
        Enforces that both source and destination remain within the workspace.
        """
        src_target = resolve_safe_path(workspace, source)
        dest_target = resolve_safe_path(workspace, destination)

        if not src_target.exists():
            raise FileNotFoundError(f"Source path not found: {source}")

        if dest_target.is_dir() or destination.endswith("/") or destination.endswith("\\"):
            dest_target.mkdir(parents=True, exist_ok=True)
            final_dest = dest_target / src_target.name
        else:
            dest_target.parent.mkdir(parents=True, exist_ok=True)
            final_dest = dest_target

        shutil.move(str(src_target), str(final_dest))
        rel_dest = str(final_dest.relative_to(workspace))
        return f"Successfully moved {source} -> {rel_dest}"

    @mcp.tool()
    def delete_file(path: str) -> str:
        """
        Safely deletes a file or directory within the workspace.
        """
        target = resolve_safe_path(workspace, path)
        if not target.exists():
            raise FileNotFoundError(f"Path not found: {path}")

        if target == workspace:
            raise PermissionError("Cannot delete root workspace directory.")

        if target.is_dir():
            shutil.rmtree(str(target))
        else:
            target.unlink()

        return f"Successfully deleted {path}"

    @mcp.tool()
    def run_command(command: str) -> Dict[str, Any]:
        """
        Executes read-only validation or discovery commands (e.g. npm -v, pytest --collect-only)
        inside the workspace root.
        """
        logger.info(f"Executing shell command in {workspace}: {command}")
        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                "command": command,
                "exit_code": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr
            }
        except subprocess.TimeoutExpired:
            return {
                "command": command,
                "exit_code": -1,
                "stdout": "",
                "stderr": "Command execution timed out after 30 seconds."
            }
        except Exception as ex:
            return {
                "command": command,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(ex)
            }

    @mcp.tool()
    def complete_preparation(
        status: str,
        detected_commands: Optional[Union[Dict[str, Optional[str]], List[Any]]] = None,
        files_modified: Optional[List[str]] = None,
        blocker_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Concludes workspace preparation, returning the final PrepSummary status and detected commands.
        Valid status: 'READY' or 'BLOCKED'.
        """
        cmds = detected_commands if isinstance(detected_commands, dict) else {}
        files = files_modified if isinstance(files_modified, list) else []
        return {
            "status": status.upper(),
            "working_directory": str(workspace),
            "detected_commands": cmds,
            "files_modified": files,
            "blocker_reason": blocker_reason
        }

    return mcp


def main():
    parser = argparse.ArgumentParser(description="Hephaestus Built-in MCP Tools Server")
    parser.add_argument(
        "--workspace",
        type=str,
        default=os.getcwd(),
        help="Target workspace root directory"
    )
    args = parser.parse_args()

    workspace_dir = Path(args.workspace).resolve()
    if not workspace_dir.exists():
        workspace_dir.mkdir(parents=True, exist_ok=True)

    server = create_builtin_mcp_server(workspace_dir)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
