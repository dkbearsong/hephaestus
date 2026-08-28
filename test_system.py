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
from backend.docker_manager.container_service import docker_manager
from backend.workflows.task_graph import workflow_engine

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

        # 4. File Gathering and Container Destination Rewriting
        dummy_file = Path("staging/task_test_1/test_source.py")
        dummy_file.parent.mkdir(parents=True, exist_ok=True)
        dummy_file.write_text("print('hello world')")

        prompt_with_files = f"<|prompt|> Review this source file.\n<|files|>\n{dummy_file}\n</|files|>"
        _, file_prompt_meta = prompt_extractor.extract_prompt(prompt_with_files, "task_test_3")
        stage_res = file_gatherer.extract_and_stage_files(
            file_prompt_meta["prompt_file_path"],
            file_prompt_meta["task_staging_dir"]
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
        prompt_internal = "<|prompt|> Implement internal cache invalidation routine on user logout."
        res_complete = workflow_engine.process_webhook_prompt(
            comment_text=prompt_internal,
            jira_issue_key="AUTH-TEST-88",
            issue_summary="User logout cache invalidation",
            project_key_hint="AUTH"
        )
        assert res_complete["status"] == "review_ready", "Expected harness to complete task inside sandbox"
        print("✅ [Coding Harness: In-Sandbox Completion] Task completed autonomously. Checkpointed container and generated Review Log.")

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
