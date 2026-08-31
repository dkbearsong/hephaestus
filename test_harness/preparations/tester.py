import os
import json
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from test_harness.base import BaseTestComponent, ComponentStatus
from backend.harness.mcp_loader import mcp_loader
from backend.preprocessor.llm_client import llm_client, LLMResponse
from backend.preprocessor.preparations_graph import preparations_runner
from backend.config import preferences, ROOT_DIR

logger = logging.getLogger("hephaestus.test_harness.preparations")

ALL_SUPPORTED_PROVIDERS = [
    "chatgpt",
    "gemini",
    "claude",
    "grok",
    "openrouter",
    "groq",
    "huggingface",
    "nvidia",
    "lm_studio",
    "ollama"
]

class PreparationsTester(BaseTestComponent):
    """
    Test Harness Component for verifying the Preparations LLM Step,
    LangGraph state machine transitions, MCP tool calling (datetime_tool, etc.),
    and multi-provider LLM compatibility (10 providers).
    """

    def __init__(self, name: str = "preparations_tester"):
        super().__init__(name=name)
        self.status = ComponentStatus.ACTIVE
        self.test_history: List[Dict[str, Any]] = []

    def log_step(self, title: str, details: Any, verbose: bool = True):
        """Prints formatted step trace during individual or batch tests."""
        if not verbose:
            return
        print(f"\n🔹 [TRACE: {title}]")
        if isinstance(details, dict):
            for k, v in details.items():
                if isinstance(v, (dict, list)):
                    print(f"   • {k}: {json.dumps(v, indent=2)}")
                else:
                    print(f"   • {k}: {v}")
        elif isinstance(details, list):
            for item in details:
                print(f"   • {item}")
        else:
            print(f"   {details}")

    def test_mcp_datetime_tool(self, verbose: bool = True) -> Dict[str, Any]:
        """
        Verifies that the Date/Time MCP tool correctly returns:
        - date only
        - time only
        - both date and time
        """
        self.log_step("Testing MCP datetime_tool", "Validating date, time, and both modes", verbose)
        errors = []
        results = {}

        try:
            # 1. Test 'date' mode
            res_date = mcp_loader.execute_tool("get_current_datetime", {"mode": "date"})
            results["date_mode"] = res_date
            if not isinstance(res_date, dict) or "date" not in res_date or res_date.get("mode") != "date":
                errors.append(f"datetime_tool 'date' mode returned invalid format: {res_date}")
            if verbose:
                self.log_step("datetime_tool (mode='date')", res_date, verbose)

            # 2. Test 'time' mode
            res_time = mcp_loader.execute_tool("get_current_datetime", {"mode": "time"})
            results["time_mode"] = res_time
            if not isinstance(res_time, dict) or "time" not in res_time or res_time.get("mode") != "time":
                errors.append(f"datetime_tool 'time' mode returned invalid format: {res_time}")
            if verbose:
                self.log_step("datetime_tool (mode='time')", res_time, verbose)

            # 3. Test 'both' mode
            res_both = mcp_loader.execute_tool("get_current_datetime", {"mode": "both"})
            results["both_mode"] = res_both
            if not isinstance(res_both, dict) or "date" not in res_both or "time" not in res_both:
                errors.append(f"datetime_tool 'both' mode returned invalid format: {res_both}")
            if verbose:
                self.log_step("datetime_tool (mode='both')", res_both, verbose)

            # 4. Test convenience functions
            date_func_res = mcp_loader.execute_tool("get_current_date", {})
            time_func_res = mcp_loader.execute_tool("get_current_time", {})
            results["get_current_date"] = date_func_res
            results["get_current_time"] = time_func_res

            success = len(errors) == 0
            outcome = {
                "test": "mcp_datetime_tool",
                "success": success,
                "results": results,
                "errors": errors
            }
            self.test_history.append(outcome)
            return outcome

        except Exception as ex:
            err_msg = f"Exception in test_mcp_datetime_tool: {ex}\n{traceback.format_exc()}"
            logger.error(err_msg)
            self._write_error_log("mcp_datetime_tool", err_msg)
            return {
                "test": "mcp_datetime_tool",
                "success": False,
                "error": str(ex),
                "traceback": traceback.format_exc()
            }

    def test_mcp_catalog_storage(self, verbose: bool = True) -> Dict[str, Any]:
        """
        Verifies discovering and storing the full catalog of available MCP tools.
        """
        self.log_step("Testing MCP Tool Catalog & Storage", "Cataloging all available tools", verbose)
        try:
            available = mcp_loader.discover_all_available_tools()
            schemas = mcp_loader.get_tool_schemas(enabled_only=False)
            catalog = mcp_loader.save_tool_catalog()

            if verbose:
                self.log_step("MCP Tool Catalog Discovered", {
                    "total_tool_modules": len(available),
                    "modules": available,
                    "total_schemas": len(schemas)
                }, verbose)

            success = "datetime_tool" in available and len(schemas) >= 3
            outcome = {
                "test": "mcp_catalog_storage",
                "success": success,
                "available_tools": available,
                "schemas_count": len(schemas),
                "catalog_file": str(ROOT_DIR / "mcp_tools" / "tool_catalog.json")
            }
            self.test_history.append(outcome)
            return outcome
        except Exception as ex:
            err_msg = f"Exception in test_mcp_catalog_storage: {ex}\n{traceback.format_exc()}"
            self._write_error_log("mcp_catalog_storage", err_msg)
            return {"test": "mcp_catalog_storage", "success": False, "error": str(ex)}

    def test_single_provider(
        self,
        provider: str,
        model: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Executes a single provider through the LangGraph preparations workflow.
        Displays each call being made, tool execution, responses, and LangGraph node transitions.
        """
        p = provider.lower().strip()
        task_id = f"test_prep_{p}_{os.urandom(3).hex()}"
        prompt = custom_prompt or "Check current date and time using datetime_tool and inspect table schemas before creating container."
        mod = model or llm_client.DEFAULT_MODELS.get(p, "default-model")

        if verbose:
            print("=" * 80)
            print(f"🚀 EXECUTING LANGGRAPH PREPARATIONS TEST FOR PROVIDER: [{p.upper()}]")
            print("=" * 80)
            self.log_step("Test Configuration", {
                "provider": p,
                "model": mod,
                "task_id": task_id,
                "preparations_prompt": prompt,
                "available_mcp_tools": mcp_loader.discover_all_available_tools()
            }, verbose)

        start_time = datetime.now(timezone.utc)
        try:
            # Run preparations LangGraph workflow
            result = preparations_runner.run_preparations(
                task_id=task_id,
                preparations_prompt=prompt,
                staging_dir=str(ROOT_DIR / "staging" / task_id),
                provider=p,
                model=mod
            )

            # Step-by-step display of LangGraph execution
            if verbose:
                step_logs = result.get("step_logs", [])
                print(f"\n📊 [LANGGRAPH EXECUTION STEPS: {len(step_logs)} Step(s) Recorded]")
                for idx, step in enumerate(step_logs, start=1):
                    step_name = step.get("step")
                    if step_name == "llm_node":
                        self.log_step(f"Step {idx}: LangGraph [LLM Node]", {
                            "iteration": step.get("iteration"),
                            "provider": step.get("provider"),
                            "model": step.get("model"),
                            "llm_content": step.get("content"),
                            "tool_calls_requested": step.get("tool_calls"),
                            "finish_reason": step.get("finish_reason"),
                            "is_end_of_token": step.get("is_end_of_token")
                        }, verbose)
                    elif step_name == "mcp_tool_node":
                        self.log_step(f"Step {idx}: LangGraph [MCP Tool Node]", {
                            "iteration": step.get("iteration"),
                            "executed_tools": step.get("executed_tools")
                        }, verbose)
                    elif step_name == "finish_node":
                        self.log_step(f"Step {idx}: LangGraph [Finish Node -> Pipeline Resumption]", {
                            "completed": step.get("completed"),
                            "end_token_received": step.get("end_token_received"),
                            "end_reason": step.get("end_reason"),
                            "final_summary": step.get("final_response")
                        }, verbose)
                    else:
                        self.log_step(f"Step {idx}: {step_name}", step, verbose)

                print("\n" + "-" * 80)
                print(f"✅ Provider [{p.upper()}] Test Completed successfully!")
                print(f"   • Completed: {result.get('completed')}")
                print(f"   • End of Token Received: {result.get('end_token_received')}")
                print(f"   • Final LLM Response: {result.get('final_response')}")
                print("-" * 80 + "\n")

            # Verification assertions
            assert result["completed"], f"Provider {p} failed to complete preparations state graph."
            assert result["end_token_received"], f"Provider {p} did not receive End of Token signal."
            assert len(result["step_logs"]) >= 2, f"Provider {p} expected at least 2 LangGraph steps."

            outcome = {
                "provider": p,
                "model": mod,
                "success": True,
                "completed": result["completed"],
                "end_token_received": result["end_token_received"],
                "step_count": len(result["step_logs"]),
                "final_response": result["final_response"],
                "step_logs": result["step_logs"]
            }
            self.test_history.append(outcome)
            return outcome

        except Exception as ex:
            err_msg = f"FAILED Provider [{p}]: {ex}\n{traceback.format_exc()}"
            print(f"\n❌ [ERROR] Provider [{p.upper()}] Failed with exception: {ex}")
            logger.error(err_msg)
            self._write_error_log(f"provider_{p}", err_msg)
            outcome = {
                "provider": p,
                "model": mod,
                "success": False,
                "error": str(ex),
                "traceback": traceback.format_exc()
            }
            self.test_history.append(outcome)
            return outcome

    def test_all_providers(self, verbose: bool = True) -> Dict[str, Any]:
        """
        Tests all 10 supported providers:
          1. chatgpt
          2. gemini
          3. claude
          4. grok
          5. openrouter
          6. groq
          7. huggingface
          8. nvidia
          9. lm_studio
          10. ollama
        """
        print("\n" + "=" * 80)
        print("   HEPHAESTUS PREPARATIONS STEP - MULTI-PROVIDER TEST SUITE (10 PROVIDERS)")
        print("=" * 80)

        # 1. Test MCP Date and Time Tool
        dt_res = self.test_mcp_datetime_tool(verbose=verbose)

        # 2. Test MCP Catalog Storage
        cat_res = self.test_mcp_catalog_storage(verbose=verbose)

        # 3. Test All 10 Providers
        provider_results = {}
        passed = 0
        failed = 0

        for prov in ALL_SUPPORTED_PROVIDERS:
            res = self.test_single_provider(provider=prov, verbose=verbose)
            provider_results[prov] = res
            if res.get("success"):
                passed += 1
            else:
                failed += 1

        total = len(ALL_SUPPORTED_PROVIDERS)
        summary = {
            "datetime_tool_test": dt_res["success"],
            "catalog_storage_test": cat_res["success"],
            "total_providers": total,
            "passed_providers": passed,
            "failed_providers": failed,
            "provider_results": provider_results,
            "all_passed": (failed == 0 and dt_res["success"] and cat_res["success"])
        }

        print("\n" + "=" * 80)
        print(f"🏁 PREPARATIONS SUITE SUMMARY: {passed}/{total} Providers Passed (Failures: {failed})")
        print(f"   • MCP Date/Time Tool Test: {'✅ PASSED' if dt_res['success'] else '❌ FAILED'}")
        print(f"   • MCP Catalog Storage Test: {'✅ PASSED' if cat_res['success'] else '❌ FAILED'}")
        print("=" * 80 + "\n")

        return summary

    def _write_error_log(self, test_name: str, error_details: str):
        """Writes detailed error log to tests/test_logs/."""
        log_dir = ROOT_DIR / "tests" / "test_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"preparations_error_{test_name}_{timestamp}.log"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n")
            f.write(f"Test Name: {test_name}\n\n")
            f.write(error_details)
        print(f"   [Error Log Saved]: {log_file}")

preparations_tester = PreparationsTester()
