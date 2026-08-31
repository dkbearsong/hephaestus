#!/usr/bin/env python3
"""
Convenience CLI launcher for the Hephaestus Live Webhook Tester.

Usage examples:
  # 1. Send a signed test webhook to the backend:
  python test_live_webhook.py send --url http://localhost:8000/api/webhooks/jira --key PAY-101 --comment "<|prompt|> Build payment retry."

  # 2. Run 3-step security verification (missing secret, tampered secret, valid secret):
  python test_live_webhook.py verify --url http://localhost:8000/api/webhooks/jira

  # 3. Launch a standalone webhook listener on port 8080 to test live Jira / ngrok deliveries:
  python test_live_webhook.py listen --port 8080

  # 4. Test 401 rejection with tampered signature or missing secret:
  python test_live_webhook.py send --tamper
  python test_live_webhook.py send --no-secret
"""
import sys
from pathlib import Path

# Ensure root directory is on PYTHONPATH
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from test_harness.webhook.live_template import main

if __name__ == "__main__":
    main()
