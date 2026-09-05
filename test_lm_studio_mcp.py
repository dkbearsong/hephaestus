#!/usr/bin/env python3
"""
LM Studio + MCP Tools Test Runner for Hephaestus
=================================================
Verifies that an AI agent hooked up to local LM Studio (http://localhost:1234/v1):
  1. Has access to the Date & Time MCP tool (mcp_tools/datetime_tool.py).
  2. Has access to the File Writer MCP tool (mcp_tools/file_writer_tool.py).
  3. Queries the current date and time via the datetime tool.
  4. Writes a .txt file named after that date and time into the project's 'outputs/' folder.
  5. Unloads the model from memory upon completion (preserving system RAM/VRAM).

Usage:
  # Standard live test with local LM Studio:
  python test_lm_studio_mcp.py

  # Test with a specific model name:
  python test_lm_studio_mcp.py --model "qwen2.5-coder-7b-instruct"

  # Test against a custom endpoint:
  python test_lm_studio_mcp.py --endpoint "http://127.0.0.1:1234/v1"

  # Force offline simulation mode (e.g. for CI or when LM Studio is not running):
  python test_lm_studio_mcp.py --simulate

  # Clean the outputs folder before running:
  python test_lm_studio_mcp.py --clean
"""

import sys
import os
import shutil
import subprocess
import json
import time
import argparse
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.config import load_user_preferences
from services.mcp_manager import MCPManager, extract_tool_result_text
from services.prep_agent import PreparationAgent, convert_mcp_tool_to_schema
from backend.preprocessor.llm_client import llm_client, LLMProviderClient
from backend.config import preferences

OUTPUTS_DIR = ROOT_DIR / "outputs"


def get_loaded_models_from_lms() -> List[str]:
    """Inspects `lms ps` to find models currently loaded in RAM/VRAM."""
    lms_bin = shutil.which("lms") or os.path.expanduser("~/.lmstudio/bin/lms")
    if not (lms_bin and os.path.exists(str(lms_bin))):
        return []
    try:
        res = subprocess.run([str(lms_bin), "ps"], capture_output=True, text=True, timeout=3)
        if res.returncode != 0:
            return []
        lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        loaded = []
        for line in lines:
            if line.startswith("IDENTIFIER") or line.startswith("No models"):
                continue
            parts = line.split()
            if parts:
                loaded.append(parts[0])
        return loaded
    except Exception:
        return []


def check_lm_studio_connection(endpoint: str = "http://localhost:1234/v1", timeout: float = 3.0) -> Dict[str, Any]:
    """
    Checks if local LM Studio is running and reachable.
    Queries GET /v1/models and `lms ps` to detect loaded models.
    """
    base_url = endpoint.rstrip("/")
    models_url = f"{base_url}/models"
    loaded_models = get_loaded_models_from_lms()
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(models_url)
            if resp.status_code == 200:
                data = resp.json()
                model_list = [m.get("id") for m in data.get("data", []) if "id" in m]
                return {
                    "reachable": True,
                    "endpoint": endpoint,
                    "models": model_list,
                    "loaded_models": loaded_models,
                    "status_code": resp.status_code
                }
    except Exception as ex:
        return {
            "reachable": False,
            "endpoint": endpoint,
            "models": [],
            "loaded_models": loaded_models,
            "error": str(ex)
        }

    return {"reachable": False, "endpoint": endpoint, "models": [], "loaded_models": loaded_models}


async def run_lm_studio_mcp_test(
    endpoint: str = "http://localhost:1234/v1",
    model: Optional[str] = None,
    simulate: bool = False,
    clean_outputs: bool = False,
    prompt: Optional[str] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Executes the end-to-end LM Studio + MCP test.
    """
    start_time = time.time()
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    if clean_outputs:
        for f in OUTPUTS_DIR.glob("*.txt"):
            try:
                f.unlink()
            except Exception:
                pass

    files_before = set(OUTPUTS_DIR.glob("*.txt"))

    if verbose:
        print("\n" + "=" * 80)
        print(" 🤖 HEPHAESTUS - LM STUDIO & MCP TOOLS INTEGRATION TEST")
        print("=" * 80)
        print(f"Target Endpoint: {endpoint}")
        print(f"Outputs Target : {OUTPUTS_DIR}")

    # Check connectivity
    conn = check_lm_studio_connection(endpoint)
    is_live = conn.get("reachable", False) and not simulate
    detected_models = conn.get("models", [])

    if is_live:
        loaded_list = conn.get("loaded_models", [])
        if model:
            chosen_model = model
        elif loaded_list:
            chosen_model = loaded_list[0]
        elif "qwen2.5-coder-1.5b-instruct-mlx" in detected_models:
            chosen_model = "qwen2.5-coder-1.5b-instruct-mlx"
        elif detected_models:
            chosen_model = detected_models[0]
        else:
            chosen_model = "local-model"

        if verbose:
            print(f"✅ LM Studio is ONLINE! Available: {detected_models or ['(default)']}")
            if loaded_list:
                print(f"⚡ Currently loaded in RAM/VRAM: {loaded_list}")
            print(f"🎯 Using Model: {chosen_model}")
    else:
        chosen_model = model or "local-model"
        if simulate:
            if verbose:
                print("ℹ️  Running in explicit SIMULATION mode (--simulate).")
        else:
            if verbose:
                print(f"⚠️  LM Studio is NOT currently reachable at {endpoint}.")
                print("   Connection error:", conn.get("error", "Server did not respond"))
                print("\n   To connect to live LM Studio:")
                print("     1. Launch LM Studio.")
                print("     2. Load any model (e.g. Qwen2.5-Coder, Llama-3.2, Mistral).")
                print("     3. Switch to the 'Developer' / 'Local Server' tab and click 'Start Server' (Port: 1234).")
                print("     4. Re-run: python test_lm_studio_mcp.py\n")
                print("👉 Falling back to deterministic SIMULATION mode for this execution.\n")

    # Update preferences endpoint if user specified custom
    if hasattr(preferences, "preparations_step") and hasattr(preferences.preparations_step, "endpoints"):
        preferences.preparations_step.endpoints["lm_studio"] = endpoint

    client = llm_client
    if not is_live:
        client = LLMProviderClient(mock_mode=True)

    # Initialize MCP Manager with datetime_tool and file_writer_tool
    pref_file = ROOT_DIR / "user-preferences.yml"
    if not pref_file.exists():
        pref_file = ROOT_DIR / "user_preferences.yaml"

    if verbose:
        print("-" * 80)
        print("📦 Starting MCP Tools (datetime_tool & file_writer_tool)...")

    test_prompt = prompt or (
        "Fetch the current date and time using the datetime tool, "
        "then use the file writer tool to write a text file named after that date and time into the outputs folder."
    )

    async with MCPManager.from_preferences(pref_file if pref_file.exists() else None, ROOT_DIR) as mcp:
        tools = await mcp.get_available_tools()
        tool_names = [t.name for t in tools]
        if verbose:
            print(f"Available MCP Tools ({len(tools)}): {', '.join(tool_names)}")

        assert "get_current_datetime" in tool_names, "datetime_tool is not loaded!"
        assert "write_datetime_output_file" in tool_names or "write_output_file" in tool_names, "file_writer_tool is not loaded!"

        # Run PreparationAgent loop with provider="lm_studio"
        agent = PreparationAgent(llm_client=client)

        if verbose:
            print("-" * 80)
            print(f"💬 Dispatching Agent Instructions:\n   \"{test_prompt}\"")
            print(f"Provider: lm_studio | Model: {chosen_model}")
            print("-" * 80)

        summary = await agent.arun(
            working_dir=ROOT_DIR,
            branch_name="test-lm-studio-mcp",
            merged_instructions=test_prompt,
            provider="lm_studio",
            model=chosen_model
        )

        # Drop model from memory if live
        if is_live:
            unload_res = client.unload_model_from_memory("lm_studio", chosen_model)
            if verbose:
                print(f"🧹 Unloaded model from LM Studio memory: {unload_res.get('status')}")

    # Inspect outputs directory
    files_after = set(OUTPUTS_DIR.glob("*.txt"))
    new_files = list(files_after - files_before)
    if not new_files and files_after:
        # Sort by modification time to find most recent
        new_files = sorted(list(files_after), key=lambda p: p.stat().st_mtime, reverse=True)[:1]

    elapsed = time.time() - start_time
    created_file = new_files[0] if new_files else None
    file_content = created_file.read_text(encoding="utf-8") if created_file and created_file.exists() else None

    result = {
        "success": bool(created_file is not None),
        "is_live": is_live,
        "endpoint": endpoint,
        "model": chosen_model,
        "elapsed_seconds": round(elapsed, 2),
        "created_file": str(created_file) if created_file else None,
        "filename": created_file.name if created_file else None,
        "file_content": file_content,
        "agent_status": summary.status
    }

    if verbose:
        print("\n" + "=" * 80)
        print(" 🏁 TEST EXECUTION SUMMARY")
        print("=" * 80)
        print(f"Status           : {'SUCCESS (Passed)' if result['success'] else 'FAILED'}")
        print(f"Execution Mode   : {'LIVE LM STUDIO' if is_live else 'SIMULATION'}")
        print(f"Model            : {chosen_model}")
        print(f"Elapsed Time     : {result['elapsed_seconds']}s")
        print(f"Output File Name : {result['filename']}")
        print(f"Output File Path : {result['created_file']}")
        if file_content:
            print("-" * 80)
            print("📄 Output File Content:")
            for line in file_content.strip().splitlines():
                print(f"   {line}")
        print("=" * 80 + "\n")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Run test connecting AI agent to local LM Studio with datetime and file writer MCP tools."
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default="http://localhost:1234/v1",
        help="LM Studio local server endpoint (default: http://localhost:1234/v1)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model identifier loaded in LM Studio (default: auto-detect from /v1/models)"
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Force simulation mode without connecting to live LM Studio"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean the outputs/ folder before running the test"
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Custom instruction prompt for the agent"
    )

    args = parser.parse_args()

    result = asyncio.run(run_lm_studio_mcp_test(
        endpoint=args.endpoint,
        model=args.model,
        simulate=args.simulate,
        clean_outputs=args.clean,
        prompt=args.prompt,
        verbose=True
    ))

    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
