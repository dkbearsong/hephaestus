#!/usr/bin/env python3
"""
CLI Runner for testing Jira tickets with the WorkspaceOrchestrator and Test Harness.
Verifies repository scaffolding, dynamic provider configuration (Google Jules, Codex Cloud, Local Container),
preparation agent behavior, and handoff state tracking.

Usage:
  # Run test ticket with interactive menu
  python run_jira_test_ticket.py --interactive

  # Run specific test ticket
  python run_jira_test_ticket.py --ticket PROJ-101 --platform LOCAL_CONTAINER --mode PROMPT_NEW

  # Run against an existing repo
  python run_jira_test_ticket.py --ticket PROJ-202 --platform GOOGLE_JULES --mode PROMPT

  # Run full verification across all platforms
  python run_jira_test_ticket.py --all-platforms

  # Query live Jira Cloud ticket
  python run_jira_test_ticket.py --ticket JIRA-2026 --live-jira
"""

import sys
import argparse
from pathlib import Path

# Ensure workspace root is in PYTHONPATH
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from test_harness.workspace_orchestrator.jira_runner import jira_ticket_workspace_runner
from test_harness.workspace_orchestrator.tester import workspace_orchestrator_tester
from test_harness.workspace_orchestrator.webhook_tester import incoming_webhook_tester


def interactive_menu():
    print("\n" + "=" * 80)
    print(" 🛠  HEPHAESTUS WORKSPACE ORCHESTRATOR - JIRA TICKET TEST HARNESS")
    print("=" * 80)
    print("Select an option:")
    print("  1. Receive Incoming Webhook (HMAC signed) and test from there")
    print("  2. Run Jira Test Ticket: PROMPT_NEW (Clean Repo Creation)")
    print("  3. Run Jira Test Ticket: PROMPT (Existing Repo Clone & Tracking Branch)")
    print("  4. Run Full Verification Across All 3 Platforms (Jules, Codex, Container)")
    print("  5. Run Custom Jira Ticket with live/simulated options")
    print("  6. Exit")
    print("-" * 80)

    choice = input("Enter choice (1-6) [default: 1]: ").strip() or "1"

    if choice == "1":
        ticket = input("Enter Jira Ticket Key [default: WEBHOOK-TEST-101]: ").strip() or "WEBHOOK-TEST-101"
        mode = input("Select Mode: 1=PROMPT_NEW, 2=PROMPT [default: 1]: ").strip()
        mode_val = "PROMPT" if mode == "2" else "PROMPT_NEW"
        plat = input("Select Platform: 1=GOOGLE_JULES, 2=CODEX_CLOUD, 3=LOCAL_CONTAINER [default: 3]: ").strip()
        plat_map = {"1": "GOOGLE_JULES", "2": "CODEX_CLOUD", "3": "LOCAL_CONTAINER"}
        plat_val = plat_map.get(plat, "LOCAL_CONTAINER")
        url = input("Optional HTTP Webhook URL (press Enter for in-process TestClient): ").strip() or None

        res = incoming_webhook_tester.receive_and_test_webhook(
            ticket_key=ticket,
            mode=mode_val,
            target_platform=plat_val,
            webhook_url=url,
            verbose=True
        )
        sys.exit(0 if res.get("success") else 1)

    elif choice == "2":
        ticket = input("Enter Jira Ticket Key [default: PROJ-NEW-101]: ").strip() or "PROJ-NEW-101"
        platform_choice = input(
            "Select Platform: 1=GOOGLE_JULES, 2=CODEX_CLOUD, 3=LOCAL_CONTAINER [default: 3]: "
        ).strip() or "3"
        plat_map = {"1": "GOOGLE_JULES", "2": "CODEX_CLOUD", "3": "LOCAL_CONTAINER"}
        target_plat = plat_map.get(platform_choice, "LOCAL_CONTAINER")

        res = jira_ticket_workspace_runner.run_and_verify_ticket(
            ticket_key=ticket,
            mode="PROMPT_NEW",
            target_platform=target_plat,
            cleanup_after=False,
            verbose=True
        )
        sys.exit(0 if res.get("success") else 1)

    elif choice == "3":
        ticket = input("Enter Jira Ticket Key [default: PROJ-EXIST-202]: ").strip() or "PROJ-EXIST-202"
        platform_choice = input(
            "Select Platform: 1=GOOGLE_JULES, 2=CODEX_CLOUD, 3=LOCAL_CONTAINER [default: 1]: "
        ).strip() or "1"
        plat_map = {"1": "GOOGLE_JULES", "2": "CODEX_CLOUD", "3": "LOCAL_CONTAINER"}
        target_plat = plat_map.get(platform_choice, "GOOGLE_JULES")

        res = jira_ticket_workspace_runner.run_and_verify_ticket(
            ticket_key=ticket,
            mode="PROMPT",
            target_platform=target_plat,
            cleanup_after=False,
            verbose=True
        )
        sys.exit(0 if res.get("success") else 1)

    elif choice == "4":
        summary = workspace_orchestrator_tester.test_all_platforms(verbose=True)
        sys.exit(0 if summary.get("all_passed") else 1)

    elif choice == "5":
        ticket = input("Enter Jira Ticket Key: ").strip() or "CUSTOM-999"
        mode_input = input("Mode (PROMPT_NEW or PROMPT) [default: PROMPT_NEW]: ").strip() or "PROMPT_NEW"
        plat_input = input("Platform (GOOGLE_JULES, CODEX_CLOUD, LOCAL_CONTAINER) [default: LOCAL_CONTAINER]: ").strip() or "LOCAL_CONTAINER"
        live_input = input("Fetch live from Jira Cloud? (y/N): ").strip().lower() == "y"
        comment = input("Custom comment prompt (optional, press Enter to use default): ").strip() or None

        res = jira_ticket_workspace_runner.run_and_verify_ticket(
            ticket_key=ticket,
            mode=mode_input,
            target_platform=plat_input,
            comment_text=comment,
            use_live_jira=live_input,
            cleanup_after=False,
            verbose=True
        )
        sys.exit(0 if res.get("success") else 1)

    else:
        print("Exiting.")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description="Run and verify Jira test tickets through the WorkspaceOrchestrator test harness."
    )
    parser.add_argument("--interactive", action="store_true", help="Launch interactive menu")
    parser.add_argument("--ticket", type=str, default="PROJ-TEST-100", help="Jira ticket key (e.g. PROJ-101)")
    parser.add_argument("--mode", choices=["PROMPT_NEW", "PROMPT"], default="PROMPT_NEW", help="Creation mode")
    parser.add_argument(
        "--platform",
        choices=["GOOGLE_JULES", "CODEX_CLOUD", "LOCAL_CONTAINER"],
        default="LOCAL_CONTAINER",
        help="Downstream target coding agent platform"
    )
    parser.add_argument("--repo-url", type=str, default=None, help="Target git repo URL for PROMPT mode")
    parser.add_argument("--comment", type=str, default=None, help="Prompt comment body")
    parser.add_argument("--live-jira", action="store_true", help="Fetch issue details from Jira Cloud API")
    parser.add_argument("--all-platforms", action="store_true", help="Run verification matrix across all platforms")
    parser.add_argument("--keep-workspace", action="store_true", help="Keep workspace directory after verification")
    parser.add_argument("--webhook", action="store_true", help="Receive an incoming signed Jira webhook and test from there")
    parser.add_argument("--webhook-url", type=str, default=None, help="Optional HTTP endpoint for webhook POST (defaults to in-process)")

    args = parser.parse_args()

    if args.interactive:
        interactive_menu()
        return

    if args.webhook:
        res = incoming_webhook_tester.receive_and_test_webhook(
            ticket_key=args.ticket,
            mode=args.mode,
            target_platform=args.platform,
            prompt=args.comment,
            webhook_url=args.webhook_url,
            verbose=True
        )
        sys.exit(0 if res.get("success") else 1)

    if args.all_platforms:
        res = workspace_orchestrator_tester.test_all_platforms(verbose=True)
        sys.exit(0 if res.get("all_passed") else 1)

    result = jira_ticket_workspace_runner.run_and_verify_ticket(
        ticket_key=args.ticket,
        mode=args.mode,
        target_platform=args.platform,
        repo_url=args.repo_url,
        comment_text=args.comment,
        use_live_jira=args.live_jira,
        cleanup_after=not args.keep_workspace,
        verbose=True
    )

    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
