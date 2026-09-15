"""
Test Runner MCP Tool for Hephaestus
Enables the coding harness agent to run test commands and report results.
"""
try:
    from mcp.server.fastmcp import FastMCP
except (ImportError, ModuleNotFoundError):
    try:
        from fastmcp import FastMCP
    except (ImportError, ModuleNotFoundError):
        from mcp.server.mcpserver import MCPServer as FastMCP
import subprocess
import os

mcp = FastMCP("Test Runner")

@mcp.tool()
def run_pytest(test_path: str = "tests", workdir: str = ".") -> dict:
    """Runs pytest on the specified directory and returns status and output."""
    try:
        res = subprocess.run(
            ["pytest", test_path, "-v"],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=120
        )
        return {
            "exit_code": res.exit_code if hasattr(res, 'exit_code') else res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "success": (res.returncode == 0)
        }
    except Exception as e:
        return {"exit_code": -1, "error": str(e), "success": False}

if __name__ == "__main__":
    mcp.run()
