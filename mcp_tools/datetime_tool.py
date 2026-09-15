"""
Date and Time MCP Tool for Hephaestus
Provides current date, current time, or both to coding and preparation agents.
"""
try:
    from mcp.server.fastmcp import FastMCP
except (ImportError, ModuleNotFoundError):
    try:
        from fastmcp import FastMCP
    except (ImportError, ModuleNotFoundError):
        from mcp.server.mcpserver import MCPServer as FastMCP
from datetime import datetime, timezone
import zoneinfo
from typing import Dict, Any, Optional

mcp = FastMCP("Date and Time Tool")

def _get_tz(tz_str: str):
    try:
        return zoneinfo.ZoneInfo(tz_str)
    except Exception:
        return timezone.utc

@mcp.tool()
def get_current_datetime(mode: str = "both", timezone_str: str = "UTC") -> Dict[str, Any]:
    """
    Returns the current date, time, or both.
    
    Args:
        mode: Which information to return: 'date', 'time', or 'both' (default is 'both').
        timezone_str: Timezone name (e.g. 'UTC', 'America/New_York', 'Europe/London', etc.). Defaults to 'UTC'.
        
    Returns:
        Dictionary containing the requested date/time details and ISO-formatted strings.
    """
    tz = _get_tz(timezone_str)
    now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    iso_str = now.isoformat()
    timestamp = now.timestamp()

    clean_mode = (mode or "both").lower().strip()

    if clean_mode == "date":
        return {
            "mode": "date",
            "date": date_str,
            "timezone": str(tz),
            "iso": date_str,
            "formatted": f"Current Date: {date_str} ({tz})"
        }
    elif clean_mode == "time":
        return {
            "mode": "time",
            "time": time_str,
            "timezone": str(tz),
            "iso": time_str,
            "formatted": f"Current Time: {time_str} ({tz})"
        }
    else: # 'both' or default
        return {
            "mode": "both",
            "date": date_str,
            "time": time_str,
            "datetime": f"{date_str} {time_str}",
            "iso": iso_str,
            "timestamp": timestamp,
            "timezone": str(tz),
            "formatted": f"Current Date & Time: {date_str} {time_str} ({tz})"
        }

@mcp.tool()
def get_current_date(timezone_str: str = "UTC") -> Dict[str, Any]:
    """Returns the current calendar date (YYYY-MM-DD)."""
    return get_current_datetime(mode="date", timezone_str=timezone_str)

@mcp.tool()
def get_current_time(timezone_str: str = "UTC") -> Dict[str, Any]:
    """Returns the current clock time (HH:MM:SS)."""
    return get_current_datetime(mode="time", timezone_str=timezone_str)

if __name__ == "__main__":
    mcp.run()
