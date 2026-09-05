#!/usr/bin/env python3
"""
Simple script to send a signed test webhook to the Hephaestus webhook receiver.
"""
import sys
import json
import hmac
import hashlib
import time
import argparse
from pathlib import Path

# Ensure root is on PYTHONPATH
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
from backend.config import JIRA_WEBHOOK_SECRET


def send_webhook(
    url: str = "http://localhost:8000/api/webhooks/jira",
    ticket_key: str = "PAY-AUTO-101",
    mode: str = "PROMPT_NEW",
    platform: str = "LOCAL_CONTAINER"
):
    secret = JIRA_WEBHOOK_SECRET or "hephaestus_webhook_secret_2026"
    prefix = "<|prompt-new|>" if mode == "PROMPT_NEW" else "<|prompt|>"
    
    comment_body = (
        f"{prefix} Implement resilient payment retry system with idempotency cache.\n\n"
        "<|preparations|>\n"
        "Ensure redis client is installed.\n"
        "Register pytest test runner.\n"
        "</|preparations|>"
    )

    agent_slug_map = {
        "GOOGLE_JULES": "google_jules",
        "CODEX_CLOUD": "openai_codex_cloud",
        "LOCAL_CONTAINER": "docker_sandbox_claude_codex"
    }

    payload = {
        "webhookEvent": "comment_created",
        "timestamp": int(time.time() * 1000),
        "issue": {
            "key": ticket_key,
            "fields": {
                "summary": f"Automated Task for {ticket_key}",
                "project": {"key": ticket_key.split("-")[0]}
            }
        },
        "comment": {
            "id": f"comment_{int(time.time())}",
            "body": comment_body,
            "author": {
                "displayName": "Jira Webhook Sender"
            }
        },
        "target_agent": agent_slug_map.get(platform, "docker_sandbox_claude_codex")
    }

    payload_bytes = json.dumps(payload).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    print(f"📡 Sending signed webhook to: {url}")
    print(f"   • Ticket Key : {ticket_key}")
    print(f"   • Mode       : {mode}")
    print(f"   • Platform   : {platform}")
    print(f"   • Signature  : sha256={signature[:16]}...")

    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": f"sha256={signature}"
    }

    try:
        resp = httpx.post(url, content=payload_bytes, headers=headers, timeout=30.0)
        print(f"\n📥 Response Code: {resp.status_code}")
        try:
            print("Response JSON:")
            print(json.dumps(resp.json(), indent=2))
        except Exception:
            print("Response Text:", resp.text)
    except Exception as e:
        print(f"❌ Failed to reach webhook endpoint: {e}")
        print("   💡 Make sure the receiver is running first: `python listen_webhooks.py`")


def main():
    parser = argparse.ArgumentParser(description="Send signed test webhook to Hephaestus receiver.")
    parser.add_argument("--url", default="http://localhost:8000/api/webhooks/jira", help="Receiver URL")
    parser.add_argument("--ticket", default="PAY-AUTO-101", help="Jira issue key")
    parser.add_argument("--mode", choices=["PROMPT_NEW", "PROMPT"], default="PROMPT_NEW", help="Mode")
    parser.add_argument("--platform", choices=["GOOGLE_JULES", "CODEX_CLOUD", "LOCAL_CONTAINER"], default="LOCAL_CONTAINER", help="Target Platform")

    args = parser.parse_args()
    send_webhook(url=args.url, ticket_key=args.ticket, mode=args.mode, platform=args.platform)


if __name__ == "__main__":
    main()
