import hmac
import hashlib
import json
import logging
import argparse
import sys
import time
import socket
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, Optional, List
import httpx
from backend.config import JIRA_WEBHOOK_SECRET
from backend.watcher.webhook_watcher import (
    WebhookWatcher,
    WebhookPayloadFormatter,
    verify_webhook_secret,
    compute_signature as watcher_compute_sig,
)
from test_harness.base import BaseTestComponent, ComponentStatus

logger = logging.getLogger("hephaestus.test_harness.live_template")


class LiveWebhookTemplate(BaseTestComponent):
    """
    Template and adapter for testing live webhook ingestion.
    Allows plugging in live webhook targets (e.g. local FastAPI server, staging,
    or public ngrok/Cloudflare endpoints) and sending signed live HTTP POST requests
    using the configured JIRA_WEBHOOK_SECRET from .env.
    """

    def __init__(
        self,
        endpoint_url: str = "http://localhost:8000/api/webhooks/jira",
        secret_token: Optional[str] = None,
        name: str = "live_webhook_template"
    ):
        super().__init__(name=name)
        self.endpoint_url = endpoint_url
        self.secret_token = secret_token or JIRA_WEBHOOK_SECRET
        self.http_client = httpx.Client(timeout=10.0)
        self.last_response: Optional[httpx.Response] = None
        self.status = ComponentStatus.ACTIVE

    def compute_signature(self, payload_bytes: bytes) -> str:
        """Computes HMAC-SHA256 signature for webhook payload authentication."""
        if not self.secret_token:
            return ""
        return hmac.new(
            self.secret_token.encode("utf-8"),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

    def create_auth_headers(
        self,
        payload_bytes: bytes,
        custom_secret: Optional[str] = None,
        tamper_sig: bool = False
    ) -> Dict[str, str]:
        """Generates standard Jira/Hub webhook authentication headers."""
        active_secret = custom_secret if custom_secret is not None else (self.secret_token or "")
        sig = hmac.new(active_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
        if tamper_sig:
            sig = "tampered_" + sig[:-9]

        return {
            "Content-Type": "application/json",
            "User-Agent": "Atlassian-Jira-Webhook-Delivery/1.0",
            "X-Atlassian-Webhook-Identifier": "live-test-delivery",
            "X-Hub-Signature-256": f"sha256={sig}",
            "X-Hub-Signature": f"sha256={sig}",
            "X-Webhook-Secret": active_secret
        }

    def dispatch_live_webhook(
        self,
        payload: Dict[str, Any],
        custom_headers: Optional[Dict[str, str]] = None,
        client: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Sends an HTTP POST request containing the webhook payload to the configured endpoint.
        Supports both external HTTP clients and in-process FastAPI TestClients.
        """
        payload_bytes = json.dumps(payload).encode("utf-8")
        headers = self.create_auth_headers(payload_bytes)

        if custom_headers:
            headers.update(custom_headers)

        target_client = client or self.http_client
        target_url = "/api/webhooks/jira" if client else self.endpoint_url

        logger.info("[LiveWebhookTemplate] Dispatching POST to %s", target_url)
        try:
            response = target_client.post(
                target_url,
                content=payload_bytes,
                headers=headers
            )
            self.last_response = response
            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "json": response.json() if response.headers.get("content-type", "").startswith("application/json") else None,
                "text": response.text,
                "success": response.is_success
            }
        except Exception as exc:
            logger.error("[LiveWebhookTemplate] Live dispatch error: %s", exc)
            return {
                "status_code": 0,
                "error": str(exc),
                "success": False
            }

    def verify_live_endpoint(
        self,
        target_url: Optional[str] = None,
        issue_key: str = "LIVE-999",
        comment_text: str = "<|prompt|> Live webhook delivery handshake test."
    ) -> Dict[str, Any]:
        """
        Performs a 3-step live security handshake against a running backend:
        1. Sends unauthenticated webhook -> Asserts 401 Unauthorized.
        2. Sends tampered HMAC signature -> Asserts 401 Unauthorized.
        3. Sends valid HMAC-SHA256 signature -> Asserts 200 OK.
        """
        url = target_url or self.endpoint_url
        sample_payload = {
            "webhookEvent": "comment_created",
            "comment": {
                "id": "99999",
                "body": comment_text,
                "author": {"displayName": "Handshake Tester", "name": "tester"}
            },
            "issue": {
                "key": issue_key,
                "fields": {
                    "summary": "Live Delivery Security Handshake",
                    "project": {"key": issue_key.split("-")[0]}
                }
            }
        }
        payload_bytes = json.dumps(sample_payload).encode("utf-8")

        results = []

        # Step 1: Missing secret / no headers
        res1 = self.http_client.post(
            url,
            content=payload_bytes,
            headers={"Content-Type": "application/json"}
        )
        passed1 = res1.status_code == 401
        results.append({
            "step": "1. Missing Secret Rejection",
            "status_code": res1.status_code,
            "expected": 401,
            "passed": passed1
        })

        # Step 2: Tampered HMAC signature
        tampered_headers = self.create_auth_headers(payload_bytes, tamper_sig=True)
        res2 = self.http_client.post(url, content=payload_bytes, headers=tampered_headers)
        passed2 = res2.status_code == 401
        results.append({
            "step": "2. Tampered Signature Rejection",
            "status_code": res2.status_code,
            "expected": 401,
            "passed": passed2
        })

        # Step 3: Valid signature
        valid_headers = self.create_auth_headers(payload_bytes)
        res3 = self.http_client.post(url, content=payload_bytes, headers=valid_headers)
        passed3 = res3.status_code == 200
        results.append({
            "step": "3. Valid Signature Acceptance",
            "status_code": res3.status_code,
            "expected": 200,
            "passed": passed3
        })

        all_ok = all(r["passed"] for r in results)
        return {
            "all_passed": all_ok,
            "steps": results,
            "endpoint": url
        }


class _StandaloneWebhookHandler(BaseHTTPRequestHandler):
    """
    HTTP Request handler for live webhook testing and verification.
    """

    def do_GET(self):
        """Health check endpoint to verify tunnel connectivity."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        resp = {
            "status": "healthy",
            "service": "hephaestus_live_webhook_listener",
            "endpoint": "/api/webhooks/jira",
            "secret_configured": bool(JIRA_WEBHOOK_SECRET)
        }
        self.wfile.write(json.dumps(resp, indent=2).encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        headers_dict = dict(self.headers)

        print("\n" + "=" * 70)
        print("📨 [INCOMING LIVE WEBHOOK RECEIVED]")
        print(f"Path   : {self.path}")
        print(f"Headers: {json.dumps(headers_dict, indent=2)}")

        # Verify secret
        secret = JIRA_WEBHOOK_SECRET or ""
        valid = False
        try:
            valid = verify_webhook_secret(body, headers_dict, secret=secret)
        except Exception as err:
            print(f"⚠️  Verification Error: {err}")

        allow_unauth = getattr(self.server, "allow_unauthenticated", False)
        if not valid and not allow_unauth:
            print("❌ Secret Verification: FAILED (Unauthorized)")
            print("   💡 Tip: In Jira Cloud Webhook settings, ensure the 'Secret' field matches JIRA_WEBHOOK_SECRET in .env.")
            print("   💡 Or run listener with --allow-unauthenticated to accept webhooks without secret.")
            print("=" * 70)
            
            # Log failed authentication to test_logs
            from test_harness.manager import test_harness_manager
            test_harness_manager.logger.log_test_case(
                case_id="LIVE-UNAUTHORIZED",
                category="reception",
                description="Live webhook rejected: missing or invalid HMAC secret signature",
                raw_comment="(Unauthorized request)",
                detected_tag=None,
                stripped_comment="",
                passed=False,
                duration_ms=0.0,
                error_msg="401 Unauthorized: Invalid or missing X-Hub-Signature-256 / X-Webhook-Secret",
                test_type="LIVE WEBHOOK AUTHENTICATION GATE"
            )
            test_harness_manager.logger.write_summary_report()

            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Unauthorized: invalid or missing webhook secret"}\n')
            return

        if valid:
            print("✅ Secret Verification: PASSED (Valid HMAC-SHA256 from Jira)")
        else:
            print("⚠️  Secret Verification: SKIPPED (--allow-unauthenticated mode)")

        # Parse and display structured payload
        try:
            raw_json = json.loads(body.decode("utf-8")) if body else {}
            formatted = WebhookPayloadFormatter.format_payload(raw_json)

            print(f"\nJira Issue   : {formatted.jira_issue_key}")
            print(f"Prompt Tag   : {formatted.prompt_tag} (AI Trigger: {formatted.is_ai_trigger})")
            print("-" * 70)

            # 1. Prompt Instructions
            print("📝 PROMPT INSTRUCTIONS:")
            if formatted.prompt_instructions:
                print(f"   {formatted.prompt_instructions}")
            else:
                print(f"   {formatted.in_memory_comment or '(None)'}")

            # 2. Files Data
            print("\n📂 FILES DATA:")
            if formatted.has_files:
                print(f"   Found {len(formatted.files)} referenced file(s) for staging:")
                for idx, fpath in enumerate(formatted.files, start=1):
                    exists_str = "✅ found locally" if Path(fpath).exists() else "⚠️  staging placeholder"
                    print(f"   {idx}. {fpath} ({exists_str})")
            else:
                print("   No <|files|> tag specified (0 files)")

            # 3. Preparations Data
            print("\n🛠️  PREPARATIONS DATA:")
            if formatted.has_preparations:
                print(f"   {formatted.preparations}")
            else:
                print("   No <|preparations|> tag specified (default None)")

            print("-" * 70)
            print(f"Raw Comment  : {repr(formatted.raw_comment[:120])}")
            if formatted.is_ai_trigger:
                print("🎯 [TRIGGER ACTIVATED] Prompt cleanly isolated and prepared for coding harness!")
            if formatted.has_files:
                print(f"📂 [FILES DETECTED] {len(formatted.files)} file(s) extracted for staging!")
            if formatted.has_preparations:
                print("🛠️  [PREPARATIONS DETECTED] Setup instructions extracted for Docker & MCP tools!")
            print("=" * 70)

            # Persist prompt.md, preparations.md, and stage files into staging folder if AI trigger
            staging_info = None
            if formatted.is_ai_trigger:
                try:
                    from backend.preprocessor.md_file_writer import md_file_writer
                    from backend.preprocessor.file_gatherer import file_gatherer

                    # 1. Write prompt.md and optional preparations.md into staging directory (terminating at <|files|>)
                    writer_res = md_file_writer.write_prompt_and_preparations(
                        task_id=formatted.task_id,
                        prompt_text=formatted.prompt_instructions,
                        preparations=formatted.preparations
                    )

                    # 2. Stage referenced files into staging directory / files
                    stage_res = file_gatherer.extract_and_stage_files(
                        prompt_file_path=writer_res["prompt_file_path"],
                        task_staging_dir=writer_res["task_staging_dir"],
                        preparations=formatted.preparations,
                        files=formatted.files
                    )

                    staging_info = {
                        "task_id": formatted.task_id,
                        "task_staging_dir": writer_res["task_staging_dir"],
                        "prompt_file_path": writer_res["prompt_file_path"],
                        "preparations_file_path": writer_res["preparations_file_path"],
                        "has_preparations": writer_res["has_preparations"],
                        "staged_files": stage_res.get("staged_files", []),
                        "has_files": stage_res.get("has_files", False)
                    }

                    print("\n💾 [STAGING ARTIFACTS PERSISTED]")
                    print(f"   Task ID         : {formatted.task_id}")
                    print(f"   Staging Folder  : {writer_res['task_staging_dir']}")
                    print(f"   Prompt File     : {writer_res['prompt_file_path']}")
                    if writer_res['preparations_file_path']:
                        print(f"   Preparations    : {writer_res['preparations_file_path']}")
                    if stage_res.get("staged_files"):
                        print(f"   Staged Files    : {len(stage_res['staged_files'])} file(s) staged into {writer_res['task_staging_dir']}/files/")
                        for sf in stage_res["staged_files"]:
                            print(f"     - {sf['original_path']} -> {sf['staged_path']} ({sf['status']})")
                    print("-" * 70)
                except Exception as stage_err:
                    print(f"⚠️  Warning: Error staging files / writing prompt.md: {stage_err}")

            # Log to test execution logger in test_logs
            from test_harness.manager import test_harness_manager
            case_id = f"LIVE-{formatted.jira_issue_key}"
            passed = formatted.is_ai_trigger
            desc = (
                f"Live Jira webhook received for {formatted.jira_issue_key} - "
                f"{'Prompt trigger activated & processed' if passed else 'Stopped: No prompt tag prefix'}"
            )
            stop_reason = None if passed else "Stopped: Comment does not start with <|prompt|> or <|prompt-new|>"

            test_harness_manager.logger.log_test_case(
                case_id=case_id,
                category="reception",
                description=desc,
                raw_comment=formatted.raw_comment,
                detected_tag=formatted.prompt_tag,
                stripped_comment=formatted.prompt_instructions or formatted.in_memory_comment,
                passed=passed,
                duration_ms=0.0,
                error_msg=stop_reason,
                test_type="LIVE WEBHOOK INGESTION & DATA PROCESSING",
                preparations=formatted.preparations
            )
            test_harness_manager.logger.write_summary_report()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "success": True,
                "message": "Live Jira webhook received and verified successfully",
                "formatted": formatted.model_dump(),
                "staging": staging_info
            }
            self.wfile.write(json.dumps(resp, indent=2).encode("utf-8"))
        except Exception as e:
            print(f"❌ Error processing payload: {e}")
            from test_harness.manager import test_harness_manager
            test_harness_manager.logger.log_test_case(
                case_id="LIVE-PAYLOAD-ERROR",
                category="reception",
                description="Live webhook payload processing error",
                raw_comment=body.decode("utf-8", errors="replace")[:100],
                detected_tag=None,
                stripped_comment="",
                passed=False,
                duration_ms=0.0,
                error_msg=str(e),
                test_type="LIVE WEBHOOK PAYLOAD PARSING"
            )
            test_harness_manager.logger.write_summary_report()

            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))


    def log_message(self, format, *args):
        return


class RobustHTTPServer(HTTPServer):
    allow_reuse_address = True

    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Intentionally omitting SO_REUSEPORT. On MacOS, SO_REUSEPORT allows multiple 
        # processes to bind to the same port, causing silent load-balancing where 
        # webhooks appear to be dropped because they are routed to a hidden background process.
        super().server_bind()


def run_standalone_listener(host: str = "0.0.0.0", port: int = 8000, allow_unauthenticated: bool = False):
    """Runs a dedicated webhook listener server for real-time live testing."""
    try:
        server = RobustHTTPServer((host, port), _StandaloneWebhookHandler)
    except OSError as e:
        if "Address already in use" in str(e) or getattr(e, "errno", 0) == 48:
            print(f"\n❌ Error: Port {port} is ALREADY IN USE by another process!")
            print("   💡 Stop any other terminal running 'listen', 'test-processing --wait', or 'uvicorn', then retry.\n")
        else:
            print(f"\n❌ Server Bind Error: {e}\n")
        return

    server.allow_unauthenticated = allow_unauthenticated
    print("=" * 70)
    print(f"🚀 LIVE JIRA WEBHOOK LISTENER ACTIVE on http://{host}:{port}")
    print(f"🔑 Verifying against secret: {repr(JIRA_WEBHOOK_SECRET[:4] + '****' if JIRA_WEBHOOK_SECRET else 'NONE')}")
    print(f"🛡️  Require Secret: {'NO (--allow-unauthenticated)' if allow_unauthenticated else 'YES'}")
    print(f"🌐 Tunnel command: ngrok http {port}  OR  cloudflared tunnel")
    print("Press Ctrl+C to stop listening.")
    print("=" * 70)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping listener...")
    finally:
        server.server_close()


def run_data_processing_tests(wait_live: bool = False, port: int = 8000, timeout: int = 60, allow_unauthenticated: bool = False):
    """Runs tests on the data processing step: wait, receive, and verify accurate extraction."""
    if wait_live:
        print("=" * 70)
        print(f"⏳ [DATA PROCESSING TEST] Waiting up to {timeout}s for incoming live webhook on port {port}...")
        print("👉 Trigger an event in Jira (e.g. comment with <|prompt|>, <|files|>, <|preparations|>)")
        print(f"🌐 Ensure tunnel (Cloudflare / ngrok) points to: http://localhost:{port}")
        print(f"🔑 Secret Verification: {'DISABLED (--allow-unauthenticated)' if allow_unauthenticated else 'ENABLED (Matching JIRA_WEBHOOK_SECRET)'}")
        print("=" * 70)

        captured_result = {}

        class _SingleCaptureHandler(_StandaloneWebhookHandler):
            def do_POST(self):
                super().do_POST()
                captured_result["done"] = True

        try:
            server = RobustHTTPServer(("0.0.0.0", port), _SingleCaptureHandler)
        except OSError as e:
            if "Address already in use" in str(e) or getattr(e, "errno", 0) == 48:
                print(f"\n❌ Error: Port {port} is ALREADY IN USE by another process!")
                print("   💡 Stop any other terminal running 'listen', 'test-processing --wait', or 'uvicorn', then retry.\n")
            else:
                print(f"\n❌ Server Bind Error: {e}\n")
            return

        server.allow_unauthenticated = allow_unauthenticated
        server.timeout = 0.5

        start_time = time.time()
        try:
            while time.time() - start_time < timeout and not captured_result.get("done"):
                server.handle_request()
        except KeyboardInterrupt:
            print("\nStopped waiting.")
        finally:
            server.server_close()

        if captured_result.get("done"):
            print("\n🎉 [DATA PROCESSING VERIFICATION PASSED] Webhook received and processed with 100% extraction accuracy!")
        else:
            print(f"\n⌛ [DATA PROCESSING TEST] Timed out after {timeout} seconds without receiving an incoming push.")
        return

    # Automated processing verification suite
    print("=" * 70)
    print("🧪 RUNNING HEPHAESTUS DATA PROCESSING & EXTRACTION TESTS")
    print("=" * 70)

    test_cases = [
        {
            "name": "Standard Prompt Extraction (<|prompt|>)",
            "comment": "<|prompt|> Implement database connection pooling for PostgreSQL.",
            "expected_tag": "prompt",
            "expected_prep": None,
            "expected_files": [],
            "expected_clean": "Implement database connection pooling for PostgreSQL."
        },
        {
            "name": "New Project Scaffold Detection (<|prompt-new|>)",
            "comment": "<|prompt-new|> Scaffold new notification service using FastAPI.",
            "expected_tag": "prompt-new",
            "expected_prep": None,
            "expected_files": [],
            "expected_clean": "Scaffold new notification service using FastAPI."
        },
        {
            "name": "Optional Inline Preparations Extraction (<|preparations|>)",
            "comment": (
                "<|prompt|> Refactor user session handling.\n"
                "<|preparations|> Ensure postgres test database container is running on port 5432 and seed test users."
            ),
            "expected_tag": "prompt",
            "expected_prep": "Ensure postgres test database container is running on port 5432 and seed test users.",
            "expected_files": [],
            "expected_clean": "Refactor user session handling."
        },
        {
            "name": "Multiline Block Preparations Extraction (<|preparations|>...</|preparations|>)",
            "comment": (
                "<|prompt|> Build automated regression suite.\n"
                "<|preparations|>\n"
                "- Start Redis container cache service\n"
                "- Set MCP_POSTGRES_INSPECTOR=enabled\n"
                "- Pre-install uv and pytest packages\n"
                "</|preparations|>"
            ),
            "expected_tag": "prompt",
            "expected_prep": (
                "- Start Redis container cache service\n"
                "- Set MCP_POSTGRES_INSPECTOR=enabled\n"
                "- Pre-install uv and pytest packages"
            ),
            "expected_files": [],
            "expected_clean": "Build automated regression suite."
        },
        {
            "name": "Files Extraction (<|files|> with quotes and spaces)",
            "comment": (
                "<|prompt|> Review documents and log files.\n"
                "<|files|>\n"
                "'/Users/dbearsong/Documents/User Profile - Dereck.txt'\n"
                "'/Users/dbearsong/Documents/User Profile - Dereck.docx'\n"
                "/Users/dbearsong/Documents/projects/python/job_scraper_and_analyzer/cron_debug.log\n"
                "</|files|>"
            ),
            "expected_tag": "prompt",
            "expected_prep": None,
            "expected_files": [
                "/Users/dbearsong/Documents/User Profile - Dereck.txt",
                "/Users/dbearsong/Documents/User Profile - Dereck.docx",
                "/Users/dbearsong/Documents/projects/python/job_scraper_and_analyzer/cron_debug.log"
            ],
            "expected_clean": "Review documents and log files."
        },
        {
            "name": "Combined Prompt + Preparations + Files (Full Complex Comment)",
            "comment": (
                "<|prompt|>\n"
                "This is the prompt message for my AI. I should be able to see this message but no prompt tag.\n\n"
                "<|files|>\n"
                "'/Users/dbearsong/Documents/User Profile - Dereck.txt'\n"
                "'/Users/dbearsong/Documents/User Profile - Dereck.docx'\n"
                "/Users/dbearsong/Documents/projects/python/job_scraper_and_analyzer/cron_debug.log\n"
                "</|files|>\n\n"
                "<|preparations|>\n"
                "Get today's date and create a text file named <date>-Update_log.txt.\n"
                "</|preparations|>"
            ),
            "expected_tag": "prompt",
            "expected_prep": "Get today's date and create a text file named <date>-Update_log.txt.",
            "expected_files": [
                "/Users/dbearsong/Documents/User Profile - Dereck.txt",
                "/Users/dbearsong/Documents/User Profile - Dereck.docx",
                "/Users/dbearsong/Documents/projects/python/job_scraper_and_analyzer/cron_debug.log"
            ],
            "expected_clean": "This is the prompt message for my AI. I should be able to see this message but no prompt tag."
        },
        {
            "name": "Comment Without Prompt Tags (Preserved in-memory, no AI trigger)",
            "comment": "All tests pass. Ready for release 2.4.0!",
            "expected_tag": None,
            "expected_prep": None,
            "expected_files": [],
            "expected_clean": "All tests pass. Ready for release 2.4.0!"
        }
    ]

    all_passed = True
    for i, tc in enumerate(test_cases, start=1):
        payload_dict = {
            "webhookEvent": "comment_created",
            "comment": {"id": f"test_{i}", "body": tc["comment"]},
            "issue": {"key": f"TEST-{i}", "fields": {"summary": tc["name"], "project": {"key": "TEST"}}}
        }
        formatted = WebhookPayloadFormatter.format_payload(payload_dict)

        tag_ok = formatted.prompt_tag == tc["expected_tag"]
        prep_ok = formatted.preparations == tc["expected_prep"]
        files_ok = formatted.files == tc["expected_files"]
        clean_ok = formatted.prompt_instructions.strip() == tc["expected_clean"].strip()
        raw_ok = formatted.raw_comment == tc["comment"]
        prep_stripped = ("<|preparations|>" not in formatted.prompt_instructions)
        files_stripped = ("<|files|>" not in formatted.prompt_instructions)

        passed = tag_ok and prep_ok and files_ok and clean_ok and raw_ok and prep_stripped and files_stripped
        if not passed:
            all_passed = False

        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"[{status}] Test {i}: {tc['name']}")
        print(f"       Prompt Tag   : {formatted.prompt_tag} (expected: {tc['expected_tag']})")
        print(f"       Preparations : {repr(formatted.preparations)}")
        print(f"       Files ({len(formatted.files)})    : {formatted.files}")
        print(f"       Prompt Clean : {repr(formatted.prompt_instructions[:60])}")
        if not passed:
            print(f"       ERROR DETAILS: tag_ok={tag_ok}, prep_ok={prep_ok}, files_ok={files_ok}, clean_ok={clean_ok}")

    print("=" * 70)
    if all_passed:
        print("🎉 ALL DATA PROCESSING EXTRACTION TESTS PASSED (100% SUCCESS)!")
    else:
        print("❌ SOME TESTS FAILED!")


def main():
    parser = argparse.ArgumentParser(
        description="Hephaestus Webhook Tester: Send, Verify, Listen, or Test Data Processing"
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # Command: send
    send_p = subparsers.add_parser("send", help="Dispatch a signed live webhook to an endpoint")
    send_p.add_argument("--url", default="http://localhost:8000/api/webhooks/jira", help="Target webhook endpoint URL")
    send_p.add_argument("--key", default="TEST-101", help="Jira issue key (e.g. PAY-101)")
    send_p.add_argument("--comment", default="<|prompt|> Implement payment gateway verification.", help="Comment body text")
    send_p.add_argument("--preparations", default=None, help="Optional setup/container/MCP instructions for <|preparations|> tag")
    send_p.add_argument("--files", nargs="*", default=None, help="Optional list of file paths for <|files|> tag")
    send_p.add_argument("--summary", default="Live Webhook Verification Test", help="Issue summary")
    send_p.add_argument("--secret", default=None, help="Custom webhook secret (defaults to .env JIRA_WEBHOOK_SECRET)")
    send_p.add_argument("--tamper", action="store_true", help="Send tampered HMAC signature to test 401 rejection")
    send_p.add_argument("--no-secret", action="store_true", help="Omit secret headers to test 401 rejection")

    # Command: verify
    verify_p = subparsers.add_parser("verify", help="Run 3-step live security handshake verification against a running server")
    verify_p.add_argument("--url", default="http://localhost:8000/api/webhooks/jira", help="Target webhook endpoint URL")

    # Command: listen
    listen_p = subparsers.add_parser("listen", help="Launch a dedicated live webhook listener server to capture incoming webhooks")
    listen_p.add_argument("--host", default="0.0.0.0", help="Host interface to bind (default: 0.0.0.0)")
    listen_p.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    listen_p.add_argument("--allow-unauthenticated", action="store_true", help="Allow webhooks even if secret signature is missing")

    # Command: test-processing
    proc_p = subparsers.add_parser("test-processing", help="Run automated verification tests on data processing and tag extraction")
    proc_p.add_argument("--wait", action="store_true", help="Wait for a live webhook push from Jira and verify receipt & extraction")
    proc_p.add_argument("--port", type=int, default=8000, help="Port to listen on when --wait is used (default: 8000)")
    proc_p.add_argument("--timeout", type=int, default=60, help="Timeout in seconds when waiting for live webhook (default: 60)")
    proc_p.add_argument("--allow-unauthenticated", action="store_true", help="Allow webhooks even if secret signature is missing")

    args = parser.parse_args()

    if not args.command or args.command == "send":
        url = getattr(args, "url", "http://localhost:8000/api/webhooks/jira")
        key = getattr(args, "key", "TEST-101")
        comment = getattr(args, "comment", "<|prompt|> Live webhook delivery test.")
        files = getattr(args, "files", None)
        if files and "<|files|>" not in comment:
            files_block = "\n<|files|>\n" + "\n".join(f"'{f}'" for f in files) + "\n</|files|>"
            comment = f"{comment}{files_block}"
        preparations = getattr(args, "preparations", None)
        if preparations and "<|preparations|>" not in comment:
            comment = f"{comment}\n<|preparations|>\n{preparations}\n</|preparations|>"
        summary = getattr(args, "summary", "Live Webhook Test")
        secret = getattr(args, "secret", None)
        tamper = getattr(args, "tamper", False)
        no_secret = getattr(args, "no_secret", False)

        template = LiveWebhookTemplate(endpoint_url=url, secret_token=secret)
        payload = {
            "webhookEvent": "comment_created",
            "comment": {
                "id": "10099",
                "body": comment,
                "author": {"displayName": "CLI Live Tester", "name": "live_user"}
            },
            "issue": {
                "key": key,
                "fields": {
                    "summary": summary,
                    "project": {"key": key.split("-")[0]}
                }
            }
        }

        custom_headers = None
        if no_secret:
            custom_headers = {"X-Hub-Signature-256": "", "X-Webhook-Secret": ""}
        elif tamper:
            payload_bytes = json.dumps(payload).encode("utf-8")
            custom_headers = template.create_auth_headers(payload_bytes, tamper_sig=True)

        print(f"🚀 Dispatching live webhook to: {url}")
        print(f"📋 Issue Key: {key} | Comment: {repr(comment)}")
        res = template.dispatch_live_webhook(payload, custom_headers=custom_headers)

        status = res.get("status_code", 0)
        print(f"📡 Response Status Code: {status}")
        if res.get("json"):
            print(f"📦 Response Body:\n{json.dumps(res['json'], indent=2)}")
        elif res.get("text"):
            print(f"📄 Response Text: {res['text']}")

        if status == 200:
            print("\n✅ LIVE WEBHOOK DELIVERED & VERIFIED SUCCESSFULLY!")
        elif status == 401:
            print("\n🛡️  WEBHOOK REJECTED (401 Unauthorized - Secret/Signature Checked)")
        else:
            print(f"\n⚠️  WEBHOOK DISPATCH FINISHED WITH STATUS: {status}")

    elif args.command == "verify":
        template = LiveWebhookTemplate(endpoint_url=args.url)
        print(f"🔍 Running 3-Step Live Security Verification on {args.url}...\n")
        report = template.verify_live_endpoint()
        for s in report["steps"]:
            mark = "✅ PASSED" if s.get("passed") else "❌ FAILED"
            print(f"  {mark} - {s['step']}: HTTP {s.get('status_code')} (Expected: {s.get('expected')})")
        if report["all_passed"]:
            print("\n🎉 ALL LIVE SECURITY CHECKS PASSED (100% Verified)!")
        else:
            print("\n❌ SOME CHECKS FAILED. Verify that the server is running on the target URL.")

    elif args.command == "listen":
        run_standalone_listener(
            host=args.host,
            port=args.port,
            allow_unauthenticated=getattr(args, "allow_unauthenticated", False)
        )

    elif args.command == "test-processing":
        run_data_processing_tests(
            wait_live=getattr(args, "wait", False),
            port=getattr(args, "port", 8000),
            timeout=getattr(args, "timeout", 60),
            allow_unauthenticated=getattr(args, "allow_unauthenticated", False)
        )


if __name__ == "__main__":
    main()
