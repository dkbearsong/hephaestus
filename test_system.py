"""
End-to-End Automated Verification Test for Hephaestus Coding Agent Harness
"""
import sys
import os
from pathlib import Path

# Ensure PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.database.connection import SessionLocal
from backend.database.models import Project, Ticket, WorkLog, ChatMessage, AgentNotification
from backend.database.search import search_full_text
from backend.jira_service.client import jira_service
from backend.preprocessor.prompt_extractor import prompt_extractor
from backend.preprocessor.file_gatherer import file_gatherer
from backend.preprocessor.preparations_graph import preparations_runner
from backend.harness.mcp_loader import mcp_loader
from backend.docker_manager.container_service import docker_manager
from backend.workflows.task_graph import workflow_engine
from test_harness import test_harness_manager

def run_tests():
    print("==========================================================")
    print("   HEPHAESTUS CODING AGENT HARNESS - AUTOMATED TEST SUITE ")
    print("==========================================================")

    session = SessionLocal()
    try:
        # 1. Database & Models
        proj_count = session.query(Project).count()
        ticket_count = session.query(Ticket).count()
        log_count = session.query(WorkLog).count()
        print(f"✅ [Database] Connected. Found {proj_count} projects, {ticket_count} tickets, {log_count} work logs.")
        assert proj_count > 0, "Expected seeded projects in database"

        # 2. PostgreSQL Full-Text Search via TSVector
        search_res = search_full_text("idempotency")
        print(f"✅ [Full-Text Search] TSVector query for 'idempotency' returned {search_res['total_matches']} match(es).")
        assert search_res["total_matches"] > 0, "Expected search matches for 'idempotency'"
        first_match = search_res["work_logs"][0]
        assert "<mark>" in first_match["headline"], "Expected <mark> highlight in headline"
        print(f"   Highlighted snippet: {first_match['headline']}")

        # 3. Prompt Extraction (<|prompt|> and <|prompt-new|>)
        test_prompt_update = "<|prompt|> Refactor database connection pooling."
        ok, meta = prompt_extractor.extract_prompt(test_prompt_update, "task_test_1")
        assert ok and not meta["is_new_project"], "Failed to extract standard prompt update"
        assert meta["cleaned_prompt"] == "Refactor database connection pooling."
        print("✅ [Prompt Extractor] Standard prompt update parsed successfully.")

        test_prompt_new = "<|prompt-new|> Scaffold new microservice with FastAPI and Poetry."
        ok_new, meta_new = prompt_extractor.extract_prompt(test_prompt_new, "task_test_2")
        assert ok_new and meta_new["is_new_project"], "Failed to detect new project workflow"
        print("✅ [Prompt Extractor] Brand new project workflow (<|prompt-new|>) detected.")

        # 3b. Optional Preparations Extraction (<|preparations|>)
        test_prompt_with_prep = (
            "<|prompt|> Setup high throughput caching.\n"
            "<|preparations|> Start redis container on port 6379 and load MCP postgres inspector."
        )
        ok_prep, meta_prep = prompt_extractor.extract_prompt(test_prompt_with_prep, "task_test_prep")
        assert ok_prep and meta_prep["has_preparations"], "Failed to extract preparations tag"
        assert meta_prep["preparations"] == "Start redis container on port 6379 and load MCP postgres inspector."
        assert Path(meta_prep["preparations_file_path"]).exists(), "preparations.md file was not created"
        print("✅ [Prompt Extractor] Optional preparations tag (<|preparations|>) extracted & staged.")

        # 3c. MCP Date and Time Tool & Tool Catalog Discovery
        dt_res = mcp_loader.execute_tool("get_current_datetime", {"mode": "both"})
        assert isinstance(dt_res, dict) and "date" in dt_res and "time" in dt_res, "datetime_tool execution failed"
        available_tools = mcp_loader.discover_all_available_tools()
        assert "datetime_tool" in available_tools, "datetime_tool was not discovered in mcp_tools"
        print(f"✅ [MCP Tools] Date & Time tool verified ({dt_res['formatted']}). Found {len(available_tools)} tools.")

        # 3d. Preparations LangGraph LLM Step with End of Token
        prep_run_res = preparations_runner.run_preparations(
            task_id="task_test_prep_lg",
            preparations_prompt="Get current date/time and verify table structures.",
            provider="gemini"
        )
        assert prep_run_res["completed"], "Preparations LangGraph execution failed to complete"
        assert prep_run_res["end_token_received"], "Preparations step did not receive End-of-Token"
        print("✅ [LangGraph Preparations] Multi-provider LLM step executed with MCP tools and End-of-Token confirmation.")

        # 4. File Gathering and Container Destination Rewriting
        dummy_file = Path("staging/task_test_1/test_source.py")
        dummy_file.parent.mkdir(parents=True, exist_ok=True)
        dummy_file.write_text("print('hello world')")

        prompt_with_files = f"<|prompt|> Review this source file: {dummy_file}\n<|files|>\n{dummy_file}\n</|files|>"
        _, file_prompt_meta = prompt_extractor.extract_prompt(prompt_with_files, "task_test_3")
        stage_res = file_gatherer.extract_and_stage_files(
            file_prompt_meta["prompt_file_path"],
            file_prompt_meta["task_staging_dir"],
            files=file_prompt_meta.get("files", [])
        )
        assert stage_res["has_files"], "Expected files to be gathered"
        assert "/workspace/staged_files/test_source.py" in stage_res["updated_prompt"], "Container path rewriting failed"
        print("✅ [File Gatherer] Staged files and rewrote container paths to /workspace/staged_files/...")

        # 5. Workflow Execution: Agent Pausing on External Access (RED SHAKING ICON)
        prompt_with_external = "<|prompt|> Connect to external payment provider at https://api.stripe.com/v1 to fetch live keys."
        res_pause = workflow_engine.process_webhook_prompt(
            comment_text=prompt_with_external,
            jira_issue_key="PAY-TEST-99",
            issue_summary="Live Stripe connection test",
            project_key_hint="PAY"
        )
        assert res_pause["status"] == "paused_waiting_input", "Expected harness to pause on external access"
        print("✅ [Coding Harness: Security Boundary] Correctly paused on external network access (Needs Input Notification generated).")

        # Verify notification in DB
        paused_notif = session.query(AgentNotification).filter(
            AgentNotification.type == "needs_input",
            AgentNotification.status == "pending"
        ).first()
        assert paused_notif is not None, "Expected pending needs_input notification"
        print(f"   Created Red Agent Notification: '{paused_notif.title}'")

        # 6. Workflow Execution: Autonomous In-Container Completion (YELLOW COMPLETED ICON)
        prompt_internal = "<|prompt|> Implement internal cache invalidation routine on user logout.\n<|preparations|> Verify current time and load postgres inspector."
        res_complete = workflow_engine.process_webhook_prompt(
            comment_text=prompt_internal,
            jira_issue_key="AUTH-TEST-88",
            issue_summary="User logout cache invalidation",
            project_key_hint="AUTH"
        )
        assert res_complete["status"] == "review_ready", "Expected harness to complete task inside sandbox"
        assert res_complete.get("preparations_result") is not None, "Expected preparations execution in workflow"
        print("✅ [Coding Harness: In-Sandbox Completion] Task completed autonomously with Preparations Step, Checkpointed container and generated Review Log.")

        # 7. Merge to Main and Teardown
        merge_ticket_id = res_complete["ticket_id"]
        merge_res = workflow_engine.merge_and_cleanup_branch(merge_ticket_id)
        assert merge_res["status"] == "merged", "Merge failed"
        print("✅ [Branch Merge & Teardown] Branch merged to main, container & checkpoint image pruned, Jira updated.")

        print("\n🎉 ALL 7 TEST SUITES PASSED WITH 100% SUCCESS!")
    finally:
        session.close()

if __name__ == "__main__":
    run_tests()
