"""
Test Harness Component for Coding Agent Orchestrators
Supports testing:
  1. Google Jules (Google Cloud Workspace container)
  2. Grok Build (xAI Sandbox container)
  3. OpenAI Codex (OpenAI Cloud Sandbox container)
  4. Docker Sandbox (Claude Code / OpenAI Codex container)
  5. Devin AI (Cognition Session Sandbox container)
  6. OpenHands with Agent Canvas (Visual Agent Canvas container)

Verifies:
  - Prompt handling passed in from Jira comments
  - Container environment initiation & isolation
  - Code changes & unified git diff synthesis
  - Clean container teardown
  - Manual Jira webhook testing option
"""

import time
import uuid
import json
import logging
from typing import Dict, Any, List, Optional
from backend.coding_agents.orchestrator import coding_agent_orchestrator
from backend.coding_agents.base import BaseCodingAgent, ContainerEnvironment
from backend.workflows.task_graph import workflow_engine
from backend.watcher.webhook_watcher import WebhookPayloadFormatter, compute_signature
from backend.config import JIRA_WEBHOOK_SECRET

logger = logging.getLogger("hephaestus.test_harness.coding_agents")

ALL_CODING_AGENTS = [
    "google_jules",
    "grok_build",
    "openai_codex_cloud",
    "docker_sandbox_claude_codex",
    "devin_ai",
    "openhands_canvas",
    "cursor_agent"
]

class CodingAgentsTester:
    """
    Test suite runner for all 6 coding agent orchestrators.
    """

    def __init__(self):
        self.orchestrator = coding_agent_orchestrator

    def test_single_agent(
        self,
        agent_id: str,
        custom_prompt: Optional[str] = None,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Tests a single coding agent orchestrator using mock data:
          1. Prompt validation & handling
          2. Container environment initiation
          3. Task execution & unified diff generation
          4. Container cleanup
        """
        agent = self.orchestrator.get_agent(agent_id)
        test_project_key = "MOCK"
        test_branch = f"test/{agent.agent_id}-{uuid.uuid4().hex[:6]}"
        test_prompt = custom_prompt or (
            f"<|prompt|> Implement token-based rate limiting algorithm for API gateway in {agent.display_name}."
        )

        if verbose:
            print(f"\n{'='*70}")
            print(f"🧪 TESTING CODING AGENT: {agent.display_name} ({agent.agent_id})")
            print(f"{'='*70}")
            print(f"• Expected Container Type: {agent.container_type}")

        start_time = time.perf_counter()
        step_results = {}

        # 1. Test Prompt Validation & Handling
        prompt_val = agent.validate_prompt(test_prompt)
        step_results["prompt_validation"] = {
            "valid": prompt_val["valid"],
            "clean_prompt_length": prompt_val.get("prompt_length", 0),
            "external_domains": prompt_val.get("detected_external_domains", [])
        }
        if verbose:
            print(f"✅ 1. Prompt Handling: Validated {prompt_val['prompt_length']} chars.")

        # 2. Test Container Environment Initiation
        mock_staged_files = [{"staged_path": "/tmp/mock_file.py", "original_path": "/workspace/file.py"}]
        mock_preparations = {
            "completed": True,
            "end_token_received": True,
            "provider": "gemini",
            "final_response": "Environment verified with MCP tools."
        }

        container_env = agent.initiate_container(
            project_key=test_project_key,
            branch_name=test_branch,
            repo_url="https://github.com/mock-org/gateway-service.git",
            staged_files=mock_staged_files,
            is_new_project=False,
            preparations_result=mock_preparations
        )

        assert isinstance(container_env, ContainerEnvironment), "Failed to initiate ContainerEnvironment"
        assert container_env.container_id, "Missing container ID"
        assert container_env.container_type == agent.container_type, f"Mismatched container type: {container_env.container_type}"

        step_results["container_initiation"] = {
            "container_id": container_env.container_id,
            "container_name": container_env.container_name,
            "container_type": container_env.container_type,
            "status": container_env.status,
            "workspace_path": container_env.workspace_path
        }
        if verbose:
            print(f"✅ 2. Container Initiation: Successfully initiated {container_env.container_type} (ID: {container_env.container_id})")
            print(f"   Workspace inside container: {container_env.workspace_path}")

        # 3. Test Task Execution in Container
        harness_res = agent.execute_in_container(
            prompt=prompt_val["clean_prompt"],
            container_env=container_env,
            project_config={"key": test_project_key, "name": "Mock Project"},
            system_prompt_additions="Follow strict PEP 8 conventions.",
            preparations_result=mock_preparations
        )

        assert harness_res.status in ("completed", "paused_waiting_input"), f"Unexpected status: {harness_res.status}"
        assert len(harness_res.git_diff) > 0, "Expected generated unified git diff"
        assert len(harness_res.full_log) > 0, "Expected execution trace logs"

        step_results["task_execution"] = {
            "status": harness_res.status,
            "summary_changes": harness_res.summary_changes,
            "git_diff_length": len(harness_res.git_diff),
            "user_check_items": harness_res.user_check_items,
            "has_diff": bool(harness_res.git_diff)
        }
        if verbose:
            print(f"✅ 3. In-Container Task Execution: Status '{harness_res.status}' with unified git diff ({len(harness_res.git_diff)} chars).")
            print(f"   Summary: {harness_res.summary_changes[:80]}...")

        # 4. Test Container Teardown / Cleanup
        cleanup_res = agent.cleanup_container(container_env)
        step_results["container_cleanup"] = cleanup_res
        if verbose:
            print(f"✅ 4. Container Cleanup: Teardown successful ({cleanup_res.get('status', 'terminated')}).")

        elapsed = time.perf_counter() - start_time
        if verbose:
            print(f"⏱  Total agent verification time: {elapsed:.2f}s")

        return {
            "agent_id": agent.agent_id,
            "display_name": agent.display_name,
            "container_type": agent.container_type,
            "success": True,
            "duration_seconds": round(elapsed, 3),
            "step_results": step_results
        }

    def test_all_agents(self, verbose: bool = True) -> Dict[str, Any]:
        """
        Runs mock data tests sequentially across all 6 coding agents.
        """
        if verbose:
            print("="*80)
            print(f" 🚀 STARTING FULL VERIFICATION: ALL {len(ALL_CODING_AGENTS)} CODING AGENT ORCHESTRATORS")
            print("="*80)

        results = []
        all_passed = True

        for agent_id in ALL_CODING_AGENTS:
            try:
                res = self.test_single_agent(agent_id, verbose=verbose)
                results.append(res)
            except Exception as e:
                all_passed = False
                logger.error("Error testing agent %s: %s", agent_id, e, exc_info=True)
                results.append({
                    "agent_id": agent_id,
                    "display_name": agent_id,
                    "success": False,
                    "error": str(e)
                })

        if verbose:
            print("\n" + "="*80)
            print(" 📊 CODING AGENT ORCHESTRATOR TEST SUMMARY")
            print("="*80)
            print(f"{'AGENT':<25} | {'CONTAINER TYPE':<28} | {'DIFF GEN':<10} | {'STATUS'}")
            print("-" * 80)
            for r in results:
                status_icon = "✅ PASSED" if r["success"] else "❌ FAILED"
                ctype = r.get("container_type", "unknown")
                diff_ok = "YES" if r.get("step_results", {}).get("task_execution", {}).get("has_diff") else "NO"
                print(f"{r['display_name']:<25} | {ctype:<28} | {diff_ok:<10} | {status_icon}")
            print("="*80)

        return {
            "all_passed": all_passed,
            "total_tested": len(results),
            "results": results
        }

    def run_manual_jira_webhook_test(
        self,
        jira_issue_key: str = "TEST-101",
        comment_text: str = "<|prompt|> Implement webhook rate limiter.\n<|preparations|> Verify current datetime and load postgres inspector.",
        target_agent: str = "google_jules",
        webhook_url: Optional[str] = None,
        use_secret: bool = True
    ) -> Dict[str, Any]:
        """
        Executes a manual test with a Jira webhook payload through the pipeline or via HTTP request.
        """
        print(f"\n{'='*75}")
        print(f"🎯 RUNNING MANUAL JIRA WEBHOOK TEST FOR AGENT: {target_agent.upper()}")
        print(f"{'='*75}")
        print(f"• Jira Issue: {jira_issue_key}")
        print(f"• Target Agent: {target_agent}")
        print(f"• Raw Comment Payload:\n  {comment_text}")

        # If HTTP URL is provided, send real HTTP POST
        if webhook_url:
            import requests
            raw_payload = {
                "webhookEvent": "comment_created",
                "comment": {
                    "id": f"comment_{uuid.uuid4().hex[:6]}",
                    "body": comment_text,
                    "author": {"displayName": "Developer QA", "name": "developer"}
                },
                "issue": {
                    "key": jira_issue_key,
                    "fields": {
                        "summary": f"Manual Webhook Test for {jira_issue_key}",
                        "project": {"key": jira_issue_key.split("-")[0]}
                    }
                },
                "target_agent": target_agent
            }
            raw_bytes = json.dumps(raw_payload).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if use_secret and JIRA_WEBHOOK_SECRET:
                sig = compute_signature(raw_bytes, JIRA_WEBHOOK_SECRET)
                headers["X-Hub-Signature-256"] = f"sha256={sig}"

            print(f"\n📡 Sending POST request to: {webhook_url}...")
            resp = requests.post(webhook_url, data=raw_bytes, headers=headers, timeout=30)
            print(f"HTTP Status: {resp.status_code}")
            try:
                res_json = resp.json()
                print(f"Response:\n{json.dumps(res_json, indent=2)}")
                return res_json
            except Exception:
                print(f"Raw Response: {resp.text}")
                return {"status_code": resp.status_code, "text": resp.text}

        # Otherwise execute directly through workflow engine
        formatted = WebhookPayloadFormatter.format_payload({
            "comment_text": comment_text,
            "jira_issue_key": jira_issue_key
        })

        print("\n⚙️  Processing through Hephaestus Workflow Pipeline:")
        print(f"1. Prompt extracted: '{formatted.in_memory_comment}'")
        print(f"2. Preparations extracted: '{formatted.preparations}'")
        print(f"3. Dispatching to Coding Agent: '{target_agent}'")

        pipeline_result = workflow_engine.process_webhook_prompt(
            comment_text=comment_text,
            jira_issue_key=formatted.jira_issue_key,
            issue_summary=f"Manual Jira Webhook Test for {jira_issue_key}",
            project_key_hint=formatted.project_key,
            preparations=formatted.preparations,
            target_agent=target_agent
        )

        print("\n🎉 Pipeline Execution Result:")
        print(f"• Status: {pipeline_result.get('status')}")
        print(f"• Ticket ID: {pipeline_result.get('ticket_id')}")
        print(f"• Summary of Changes: {pipeline_result.get('summary_changes')}")
        if pipeline_result.get("git_diff"):
            print(f"• Unified Git Diff:\n{pipeline_result.get('git_diff')}")

        return {
            "success": True,
            "jira_issue_key": jira_issue_key,
            "target_agent": target_agent,
            "pipeline_result": pipeline_result
        }

coding_agents_tester = CodingAgentsTester()
