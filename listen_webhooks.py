#!/usr/bin/env python3
"""
Hephaestus Webhook Listener Daemon

Launches the webhook receiver with ZERO prompts (no ticket requested).
Sits actively listening for incoming Jira Cloud webhooks (or curl/Postman),
processes them through the pipeline and WorkspaceOrchestrator, and verifies the resulting workspace.

Usage:
  # 1. Start listening on default port 8000 (no questions asked):
  python listen_webhooks.py

  # 2. Start listening on custom port:
  python listen_webhooks.py --port 8080

  # 3. Test the entire process immediately without running a background server:
  python listen_webhooks.py --test-once
"""

import sys
import argparse
from pathlib import Path

# Ensure root directory is on PYTHONPATH
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import JIRA_WEBHOOK_SECRET


def print_banner(host: str, port: int):
    endpoint = f"http://{host}:{port}/api/webhooks/jira"
    secret = JIRA_WEBHOOK_SECRET or "hephaestus_webhook_secret_2026"
    print("\n" + "=" * 80)
    print(" 🚀 HEPHAESTUS WEBHOOK RECEIVER IS LIVE & LISTENING")
    print("=" * 80)
    print(f" • Webhook Endpoint : {endpoint}")
    print(f" • Expected Secret  : {secret}")
    print(f" • Auth Header      : X-Hub-Signature-256: sha256=<hmac_sha256>")
    print(" • Status           : Waiting for incoming webhooks...")
    print(" • Mode             : Automatic (reads ticket, prompt, preparations from payload)")
    print("-" * 80)
    print(" 💡 To test sending an incoming webhook to this listener, in another terminal run:")
    print("    python send_test_webhook.py")
    print("\n 💡 Or using curl:")
    print(f"    curl -X POST {endpoint} \\")
    print('      -H "Content-Type: application/json" \\')
    print('      -H "X-Webhook-Secret: ' + secret + '" \\')
    print('      -d \'{"webhookEvent":"comment_created","issue":{"key":"PAY-101"},"comment":{"body":"<|prompt-new|> Build payment queue."}}\'')
    print("=" * 80 + "\n")


def run_test_once():
    """Runs a complete test from an incoming webhook with zero prompts."""
    print("\n" + "=" * 80)
    print("🧪 RUNNING ONE-SHOT INCOMING WEBHOOK TEST (ZERO PROMPTS)")
    print("=" * 80)
    from test_harness.workspace_orchestrator.webhook_tester import incoming_webhook_tester
    
    res = incoming_webhook_tester.receive_and_test_webhook(
        ticket_key="LIVE-WEBHOOK-AUTO",
        mode="PROMPT_NEW",
        target_platform="LOCAL_CONTAINER",
        prompt="Build resilient event-driven retry queue with Redis.",
        preparations="Configure pytest test suite and mount points.\n",
        verbose=True
    )
    sys.exit(0 if res.get("success") else 1)


def main():
    parser = argparse.ArgumentParser(
        description="Hephaestus Webhook Listener Daemon - Receives webhooks and processes workspaces with zero prompts."
    )
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host interface to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument(
        "--test-once",
        action="store_true",
        help="Simulate an incoming webhook, process it through WorkspaceOrchestrator, and verify the result immediately"
    )

    args = parser.parse_args()

    if args.test_once:
        run_test_once()
        return

    print_banner(args.host, args.port)

    import uvicorn
    uvicorn.run("backend.main:app", host=args.host, port=args.port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
