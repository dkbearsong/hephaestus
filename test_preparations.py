#!/usr/bin/env python3
"""
Interactive & Automated Test Runner for Hephaestus Preparations LLM Step
Supports testing:
  - 10 LLM Providers (ChatGPT, Gemini, Claude, Grok, OpenRouter, Groq, HuggingFace, Nvidia, LM Studio, Ollama)
  - MCP Date and Time Tool (date, time, both modes)
  - Full MCP Tool Catalog Discovery and Storage
  - Step-by-step LangGraph node execution and trace inspection
"""
import sys
import os
import argparse
from pathlib import Path

# Ensure project root is in PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_harness import preparations_tester
from test_harness.preparations.tester import ALL_SUPPORTED_PROVIDERS
from backend.harness.mcp_loader import mcp_loader
from backend.config import ROOT_DIR

def main():
    parser = argparse.ArgumentParser(
        description="Hephaestus Preparations LLM Step & MCP Tools Test Harness Runner"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run full automated verification across all 10 providers and MCP tools"
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help=f"Test a specific provider. Options: {', '.join(ALL_SUPPORTED_PROVIDERS)}"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Specify an explicit model name for the provider"
    )
    parser.add_argument(
        "--tool",
        type=str,
        default=None,
        help="Test a specific MCP tool (e.g. 'datetime_tool', 'postgres_inspector', 'test_runner')"
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Custom preparations prompt to feed into the LangGraph state machine"
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Discover and list all available MCP tools in the catalog"
    )

    args = parser.parse_args()

    # If no arguments passed, default to running all tests
    if len(sys.argv) == 1 or args.all:
        summary = preparations_tester.test_all_providers(verbose=True)
        if not summary["all_passed"]:
            print("❌ Some test suites failed. Check logs above and in tests/test_logs/.")
            sys.exit(1)
        else:
            print("🎉 ALL PREPARATIONS TESTS PASSED SUCCESSFULLY (10/10 Providers + MCP Tools)!")
            sys.exit(0)

    if args.list_tools:
        available = mcp_loader.discover_all_available_tools()
        schemas = mcp_loader.get_tool_schemas(enabled_only=False)
        print("\n📦 DISCOVERED MCP TOOLS CATALOG:")
        print(f"Total Available Modules: {len(available)}")
        for mod in available:
            print(f"  • {mod}")
        print(f"\nTotal Discovered Function Schemas: {len(schemas)}")
        for s in schemas:
            func = s.get("function", {})
            print(f"  • {func.get('name')}: {func.get('description')[:70]}...")
        catalog = mcp_loader.save_tool_catalog()
        print(f"\nSaved full catalog to: {ROOT_DIR / 'mcp_tools' / 'tool_catalog.json'}\n")
        return

    if args.tool:
        tool_name = args.tool.lower().strip()
        if "date" in tool_name or "time" in tool_name:
            res = preparations_tester.test_mcp_datetime_tool(verbose=True)
            if not res["success"]:
                sys.exit(1)
        else:
            schemas = mcp_loader.get_tool_schemas(enabled_only=False)
            print(f"\nTesting MCP tool '{tool_name}'...")
            matching = [s for s in schemas if tool_name in s.get("function", {}).get("name", "")]
            print(f"Found {len(matching)} matching tool functions: {[m['function']['name'] for m in matching]}")
            return

    if args.provider:
        prov = args.provider.lower().strip()
        if prov not in ALL_SUPPORTED_PROVIDERS:
            print(f"❌ Unknown provider '{prov}'. Supported options: {', '.join(ALL_SUPPORTED_PROVIDERS)}")
            sys.exit(1)

        result = preparations_tester.test_single_provider(
            provider=prov,
            model=args.model,
            custom_prompt=args.prompt,
            verbose=True
        )

        if not result.get("success"):
            print(f"❌ Test failed for provider '{prov}'. See error trace above.")
            sys.exit(1)
        else:
            print(f"🎉 Provider '{prov}' successfully executed LangGraph preparations and received End-of-Token!")
            sys.exit(0)

if __name__ == "__main__":
    main()
