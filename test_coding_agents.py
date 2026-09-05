#!/usr/bin/env python3
"""
Test Suite & Manual Jira Webhook Runner for Hephaestus Coding Agent Orchestrators
Supports testing:
  1. Google Jules (Google Cloud Workspace container)
  2. Grok Build (xAI Sandbox container)
  3. OpenAI Codex (OpenAI Cloud Sandbox container)
  4. Docker Sandbox (Claude Code / OpenAI Codex container)
  5. Devin AI (Cognition Session Sandbox container)
  6. OpenHands with Agent Canvas (Visual Agent Canvas container)

Options:
  --all                 Run mock tests for all 6 coding agent orchestrators
  --agent <name>        Test a specific coding agent
  --jira-manual         Run manual test with a webhook from Jira
  --key <issue_key>     Jira issue key (e.g. PAY-101)
  --comment <text>      Comment prompt text (e.g. "<|prompt|> Build feature")
  --url <endpoint>      Optional HTTP endpoint URL (e.g. http://localhost:8000/api/webhooks/jira)
  --interactive         Launch interactive test selector
"""

import sys
import os
import argparse
from pathlib import Path

# Ensure project root is in PYTHONPATH
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from test_harness.coding_agents.tester import coding_agents_tester, ALL_CODING_AGENTS
from test_harness.workspace_orchestrator import (
    jira_ticket_workspace_runner,
    workspace_orchestrator_tester,
    incoming_webhook_tester
)
from backend.coding_agents.orchestrator import coding_agent_orchestrator

def run_interactive():
    print("\n" + "="*75)
    print(" 🛠  HEPHAESTUS CODING AGENT ORCHESTRATOR - INTERACTIVE TEST CONSOLE")
    print("="*75)
    print("Select a test option:")
    print("  1. Run automated mock verification on ALL 6 coding agents")
    print("  2. Test a specific coding agent")
    print("  3. Run MANUAL test with a webhook from Jira")
    print("  4. List all supported coding agents & container environments")
    print("  5. Run Jira Test Ticket with WorkspaceOrchestrator (Scaffolding, Provider Prep & Handoff)")
    print("  6. Receive Incoming Webhook and Test WorkspaceOrchestrator From There")
    print("  7. Exit")
    print("-" * 75)

    choice = input("Enter choice (1-7): ").strip()
    if choice == "1":
        summary = coding_agents_tester.test_all_agents(verbose=True)
        sys.exit(0 if summary["all_passed"] else 1)
    elif choice == "2":
        print("\nAvailable Coding Agents:")
        for idx, a in enumerate(ALL_CODING_AGENTS, 1):
            print(f"  {idx}. {a}")
        sub_choice = input(f"Select agent (1-{len(ALL_CODING_AGENTS)}) or enter name: ").strip()
        if sub_choice.isdigit() and 1 <= int(sub_choice) <= len(ALL_CODING_AGENTS):
            target = ALL_CODING_AGENTS[int(sub_choice) - 1]
        else:
            target = sub_choice
        res = coding_agents_tester.test_single_agent(target, verbose=True)
        sys.exit(0 if res.get("success") else 1)
    elif choice == "3":
        print("\n--- Manual Jira Webhook Test Configuration ---")
        issue_key = input("Enter Jira Issue Key [default: JIRA-2026]: ").strip() or "JIRA-2026"
        default_comment = "<|prompt|> Implement secure JWT token rotation and add pytest test cases.\n<|preparations|> Verify current time and test database access."
        print(f"\nEnter comment prompt [press Enter for default]:")
        comment_in = input(f"Default: '{default_comment[:50]}...'\n> ").strip()
        comment = comment_in or default_comment
        
        print("\nSelect target coding agent:")
        for idx, a in enumerate(ALL_CODING_AGENTS, 1):
            print(f"  {idx}. {a}")
        agent_choice = input(f"Select agent (1-{len(ALL_CODING_AGENTS)}) [default: 1]: ").strip()
        if agent_choice.isdigit() and 1 <= int(agent_choice) <= len(ALL_CODING_AGENTS):
            target_agent = ALL_CODING_AGENTS[int(agent_choice) - 1]
        else:
            target_agent = agent_choice or "google_jules"

        url = input("\nOptional HTTP target URL (press Enter to run in-process pipeline): ").strip() or None
        coding_agents_tester.run_manual_jira_webhook_test(
            jira_issue_key=issue_key,
            comment_text=comment,
            target_agent=target_agent,
            webhook_url=url
        )
        sys.exit(0)
    elif choice == "4":
        agents = coding_agent_orchestrator.list_supported_agents()
        print("\n📦 SUPPORTED CODING AGENTS & CONTAINER TYPES:")
        for a in agents:
            print(f"  • {a['display_name']} ({a['agent_id']}) -> Container: {a['container_type']}")
        sys.exit(0)
    elif choice == "5":
        print("\n--- Jira Ticket WorkspaceOrchestrator Test ---")
        ticket = input("Enter Jira Ticket Key [default: JIRA-ORCH-101]: ").strip() or "JIRA-ORCH-101"
        mode = input("Select Mode: 1=PROMPT_NEW, 2=PROMPT [default: 1]: ").strip()
        mode_val = "PROMPT" if mode == "2" else "PROMPT_NEW"
        plat = input("Select Platform: 1=GOOGLE_JULES, 2=CODEX_CLOUD, 3=LOCAL_CONTAINER [default: 3]: ").strip()
        plat_map = {"1": "GOOGLE_JULES", "2": "CODEX_CLOUD", "3": "LOCAL_CONTAINER"}
        plat_val = plat_map.get(plat, "LOCAL_CONTAINER")
        live = input("Fetch from live Jira Cloud API? (y/N): ").strip().lower() == "y"
        res = jira_ticket_workspace_runner.run_and_verify_ticket(
            ticket_key=ticket,
            mode=mode_val,
            target_platform=plat_val,
            use_live_jira=live,
            cleanup_after=False,
            verbose=True
        )
        sys.exit(0 if res.get("success") else 1)
    elif choice == "6":
        print("\n--- Incoming Webhook WorkspaceOrchestrator Test ---")
        ticket = input("Enter Jira Ticket Key [default: WEBHOOK-TEST-505]: ").strip() or "WEBHOOK-TEST-505"
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
    else:
        print("Exiting.")
        sys.exit(0)

def main():
    parser = argparse.ArgumentParser(
        description="Hephaestus Coding Agent Orchestrator & Jira Webhook Test Suite"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run full automated verification across all 6 coding agent orchestrators"
    )
    parser.add_argument(
        "--agent",
        type=str,
        default=None,
        help=f"Test a specific coding agent. Options: {', '.join(ALL_CODING_AGENTS)}"
    )
    parser.add_argument(
        "--jira-manual",
        action="store_true",
        help="Run manual test with a webhook from Jira"
    )
    parser.add_argument(
        "--key",
        type=str,
        default="JIRA-2026",
        help="Jira issue key for manual webhook test (e.g. PAY-101)"
    )
    parser.add_argument(
        "--comment",
        type=str,
        default="<|prompt|> Implement secure JWT token rotation and add pytest test cases.\n<|preparations|> Verify current time and test database access.",
        help="Comment prompt text for manual webhook test"
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Optional HTTP URL to dispatch webhook POST request (e.g. http://localhost:8000/api/webhooks/jira)"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Launch interactive test selector"
    )
    parser.add_argument(
        "--list-agents",
        action="store_true",
        help="List all supported coding agents and their container environments"
    )
    parser.add_argument(
        "--jira-workspace-ticket",
        type=str,
        default=None,
        help="Run WorkspaceOrchestrator test for a specific Jira ticket (e.g. PROJ-101)"
    )
    parser.add_argument(
        "--workspace-mode",
        choices=["PROMPT_NEW", "PROMPT"],
        default="PROMPT_NEW",
        help="Workspace mode for --jira-workspace-ticket"
    )
    parser.add_argument(
        "--workspace-platform",
        choices=["GOOGLE_JULES", "CODEX_CLOUD", "LOCAL_CONTAINER"],
        default="LOCAL_CONTAINER",
        help="Target platform for --jira-workspace-ticket"
    )
    parser.add_argument(
        "--webhook-orchestrator",
        action="store_true",
        help="Receive an incoming signed Jira webhook and test WorkspaceOrchestrator from there"
    )

    args = parser.parse_args()

    if args.interactive:
        run_interactive()
        return

    if args.webhook_orchestrator:
        res = incoming_webhook_tester.receive_and_test_webhook(
            ticket_key=args.jira_workspace_ticket or "WEBHOOK-TEST-505",
            mode=args.workspace_mode,
            target_platform=args.workspace_platform,
            prompt=args.comment if args.comment != parser.get_default("comment") else None,
            webhook_url=args.url,
            verbose=True
        )
        sys.exit(0 if res.get("success") else 1)

    if args.all_workspace_platforms:
        res = workspace_orchestrator_tester.test_all_platforms(verbose=True)
        sys.exit(0 if res.get("all_passed") else 1)

    if args.jira_workspace_ticket:
        res = jira_ticket_workspace_runner.run_and_verify_ticket(
            ticket_key=args.jira_workspace_ticket,
            mode=args.workspace_mode,
            target_platform=args.workspace_platform,
            comment_text=args.comment if args.comment != parser.get_default("comment") else None,
            cleanup_after=False,
            verbose=True
        )
        sys.exit(0 if res.get("success") else 1)

    if args.list_agents:
        agents = coding_agent_orchestrator.list_supported_agents()
        print("\n📦 SUPPORTED CODING AGENTS & CONTAINER TYPES:")
        for a in agents:
            print(f"  • {a['display_name']} ({a['agent_id']}) -> Container: {a['container_type']}")
        return

    if args.jira_manual:
        target_agent = args.agent or "google_jules"
        coding_agents_tester.run_manual_jira_webhook_test(
            jira_issue_key=args.key,
            comment_text=args.comment,
            target_agent=target_agent,
            webhook_url=args.url
        )
        return

    if args.agent:
        res = coding_agents_tester.test_single_agent(args.agent, verbose=True)
        sys.exit(0 if res.get("success") else 1)

    # Default: Run all mock tests
    summary = coding_agents_tester.test_all_agents(verbose=True)
    if not summary["all_passed"]:
        print("❌ Some coding agent test suites failed.")
        sys.exit(1)
    else:
        print(f"\n🎉 ALL {summary['total_tested']} CODING AGENT ORCHESTRATORS PASSED AUTOMATED VERIFICATION WITH 100% SUCCESS!")
        print("💡 Tip: Use `python test_coding_agents.py --jira-manual --agent <name>` to run a manual Jira webhook test.")
        sys.exit(0)

if __name__ == "__main__":
    main()
