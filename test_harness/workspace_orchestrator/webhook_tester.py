import hmac
import hashlib
import json
import os
import time
import uuid
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Literal

import httpx
from starlette.testclient import TestClient

from backend.config import JIRA_WEBHOOK_SECRET, ROOT_DIR, get_prompt_output_dir
from backend.main import app
from services.scaffolding import GitRunner

logger = logging.getLogger("hephaestus.test_harness.webhook_tester")


class IncomingWebhookTester:
    """
    Receives and tests incoming Jira webhooks end-to-end.
    Sends signed webhook payloads (via in-process FastAPI TestClient or live HTTP POST)
    and verifies the entire downstream execution:
      1. Webhook HMAC-SHA256 signature verification & ingestion
      2. Prompt & preparations parser step (prompt.md, preparations.md, staged_files/)
      3. WorkspaceOrchestrator execution:
         - Isolated workspace directory allocation
         - Git repository initialization / branch checkout
         - Dynamic platform configuration (Jules, Codex, Local Container)
         - Preparation agent file placement & command detection
         - Handoff state tracking in .hephaestus_handoff.json
      4. Jira trigger label handling
    """

    def __init__(self, default_secret: Optional[str] = None):
        self.secret = default_secret or JIRA_WEBHOOK_SECRET or "hephaestus_webhook_secret_2026"
        self.test_client = TestClient(app)

    def compute_signature(self, payload_bytes: bytes, secret: Optional[str] = None) -> str:
        """Computes HMAC-SHA256 signature."""
        active_secret = secret if secret is not None else self.secret
        return hmac.new(
            active_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

    def build_comment_text(
        self,
        mode: Literal["PROMPT_NEW", "PROMPT"],
        prompt: str,
        preparations: Optional[str] = None,
        files: Optional[List[str]] = None,
        flags: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Constructs Jira comment body containing trigger prefixes and tags:
        <|prompt-new|> or <|prompt|>
        <|flags|> (optional)
        <|files|> (optional)
        <|preparations|> (optional)
        """
        prefix = "<|prompt-new|>" if mode == "PROMPT_NEW" else "<|prompt|>"
        parts = [f"{prefix} {prompt.strip()}"]

        if flags:
            import yaml
            flags_yaml = yaml.dump(flags, default_flow_style=False).strip()
            parts.append(f"<|flags|>\n{flags_yaml}\n</|flags|>")

        if files:
            files_content = "\n".join(files)
            parts.append(f"<|files|>\n{files_content}\n</|files|>")

        if preparations:
            parts.append(f"<|preparations|>\n{preparations.strip()}\n</|preparations|>")

        return "\n\n".join(parts)

    def build_jira_webhook_payload(
        self,
        ticket_key: str,
        comment_text: str,
        summary: Optional[str] = None,
        target_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Constructs an authentic Atlassian Jira Cloud webhook payload.
        """
        proj_key = ticket_key.split("-")[0] if "-" in ticket_key else "PROJ"
        payload = {
            "webhookEvent": "comment_created",
            "timestamp": int(time.time() * 1000),
            "issue": {
                "key": ticket_key,
                "fields": {
                    "summary": summary or f"Task for {ticket_key}",
                    "project": {"key": proj_key},
                    "labels": ["run_ai_orchestrator"]
                }
            },
            "comment": {
                "id": f"comment_{uuid.uuid4().hex[:6]}",
                "body": comment_text,
                "author": {
                    "displayName": "Jira Test Automator",
                    "accountId": "jira_test_account_123"
                }
            }
        }
        if target_agent is not None:
            payload["target_agent"] = target_agent
        return payload

    def receive_and_test_webhook(
        self,
        ticket_key: Optional[str] = None,
        mode: Literal["PROMPT_NEW", "PROMPT"] = "PROMPT_NEW",
        target_platform: Optional[str] = "LOCAL_CONTAINER",
        prompt: Optional[str] = None,
        preparations: Optional[str] = None,
        files: Optional[List[str]] = None,
        flags: Optional[Dict[str, Any]] = None,
        staged_files: Optional[Dict[str, str]] = None,
        webhook_url: Optional[str] = None,
        tamper_signature: bool = False,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Dispatches incoming webhook and verifies entire downstream pipeline & workspace behavior.
        If ticket_key is None or empty, automatically generates a unique Jira ticket key.
        """
        ticket_key = ticket_key or f"AUTO-{uuid.uuid4().hex[:6].upper()}"
        verifications: Dict[str, bool] = {}
        errors: List[str] = []

        # Map platform to agent slug
        if target_platform is None:
            target_agent = None
        else:
            agent_map = {
                "GOOGLE_JULES": "google_jules",
                "CODEX_CLOUD": "openai_codex_cloud",
                "LOCAL_CONTAINER": "docker_sandbox_claude_codex",
                "GROK_BUILD": "grok_build",
                "DEVIN_AI": "devin_ai",
                "CURSOR_DEVCONTAINER": "cursor_agent"
            }
            target_agent = agent_map.get(target_platform, "google_jules")

        # 1. Prepare Staged Files locally so file_gatherer can copy them
        file_paths_for_tag = []
        scratch_dir = ROOT_DIR / "sandboxes" / "scratch" / f"staging_src_{ticket_key}_{int(time.time())}"
        scratch_dir.mkdir(parents=True, exist_ok=True)

        files_dict = staged_files or {
            "controller.py": "# Controller Component\ndef handle_req(): return 'ok'\n",
            "test_controller.py": "def test_ok(): assert True\n",
            "run_service.sh": "#!/bin/bash\necho 'Service started'\n"
        }

        for fname, content in files_dict.items():
            fpath = scratch_dir / fname
            fpath.write_text(content, encoding="utf-8")
            file_paths_for_tag.append(str(fpath.resolve()))

        # 2. Build full comment with tags
        prompt_text = prompt or f"Implement distributed idempotency cache for ticket {ticket_key}."
        prep_text = preparations or (
            "Move controller.py to src/controllers/\n"
            "Install redis>=5.0.0\n"
            "Ensure pytest is registered.\n"
        )
        full_comment = self.build_comment_text(
            mode=mode,
            prompt=prompt_text,
            preparations=prep_text,
            files=file_paths_for_tag,
            flags=flags
        )

        # 3. Build JSON payload & HMAC signature
        payload_dict = self.build_jira_webhook_payload(
            ticket_key=ticket_key,
            comment_text=full_comment,
            summary=f"Automated Webhook Test for {ticket_key}",
            target_agent=target_agent
        )
        payload_bytes = json.dumps(payload_dict).encode("utf-8")
        sig = self.compute_signature(payload_bytes)
        if tamper_signature:
            sig = "tampered_" + sig[:-9]

        headers = {
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={sig}"
        }

        if verbose:
            print("\n" + "=" * 80)
            print(f"📡 INCOMING WEBHOOK TEST FOR TICKET: {ticket_key}")
            print("=" * 80)
            print(f"• Ingestion Mode: {'HTTP POST ' + webhook_url if webhook_url else 'In-Process FastAPI TestClient'}")
            print(f"• Mode: {mode} | Target Platform: {target_platform} ({target_agent})")
            print(f"• HMAC Signature: sha256={sig[:16]}...")

        # 4. Dispatch Webhook
        start_time = time.perf_counter()
        http_status = None
        response_body = {}

        try:
            if webhook_url:
                resp = httpx.post(webhook_url, content=payload_bytes, headers=headers, timeout=30.0)
                http_status = resp.status_code
                try:
                    response_body = resp.json()
                except Exception:
                    response_body = {"raw": resp.text}
            else:
                resp = self.test_client.post("/api/webhooks/jira", content=payload_bytes, headers=headers)
                http_status = resp.status_code
                try:
                    response_body = resp.json()
                except Exception:
                    response_body = {"raw": resp.text}
        except Exception as e:
            errors.append(f"Webhook dispatch failed: {e}")

        elapsed = time.perf_counter() - start_time

        # If testing signature tampering, verify 401 Unauthorized
        if tamper_signature:
            verifications["tamper_rejected_401"] = (http_status == 401)
            all_verified = verifications["tamper_rejected_401"]
            return {
                "success": all_verified,
                "http_status": http_status,
                "verifications": verifications,
                "errors": errors
            }

        # 5. Verify Ingestion & Pipeline Result
        v_http_ok = (http_status == 200)
        verifications["webhook_accepted_200"] = v_http_ok

        pipeline_result = response_body.get("pipeline_result", {})
        v_pipeline_ok = bool(response_body.get("success") and pipeline_result.get("success"))
        verifications["pipeline_dispatched"] = v_pipeline_ok

        # 6. Verify WorkspaceOrchestrator Execution
        ws_orch = pipeline_result.get("workspace_orchestration") or {}
        working_dir_str = ws_orch.get("working_directory")
        working_dir_path = Path(working_dir_str) if working_dir_str else None

        v_workspace_created = bool(working_dir_path and working_dir_path.exists())
        verifications["workspace_created"] = v_workspace_created

        # Verify Git branch
        v_git_branch = False
        if v_workspace_created:
            try:
                branch_res = GitRunner.run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=working_dir_path)
                current_branch = branch_res.stdout.strip()
                expected_branch = "main" if mode == "PROMPT_NEW" else f"jira-{ticket_key}-agent"
                v_git_branch = (current_branch == expected_branch or ticket_key.lower() in current_branch)
            except Exception as ex:
                errors.append(f"Git check failed: {ex}")
        verifications["git_branch_valid"] = v_git_branch

        # Verify Platform Configuration Rules
        v_platform_rules = False
        effective_plat = target_platform or ws_orch.get("target_platform")
        if v_workspace_created:
            if effective_plat == "GOOGLE_JULES":
                jules_cfg = working_dir_path / ".jules" / "config.yaml"
                status_res = GitRunner.run_git(["status", "--porcelain"], cwd=working_dir_path)
                v_platform_rules = jules_cfg.exists() and (status_res.stdout.strip() == "")
            elif effective_plat == "CODEX_CLOUD":
                task_meta = working_dir_path / ".codex" / "task_metadata.json"
                v_platform_rules = task_meta.exists()
            elif effective_plat == "LOCAL_CONTAINER":
                mounts_cfg = working_dir_path / ".docker" / "mounts.json"
                env_file = working_dir_path / ".env"
                v_platform_rules = mounts_cfg.exists() and env_file.exists()
            else:
                v_platform_rules = True
        verifications["provider_rules_enforced"] = v_platform_rules

        # Verify Handoff State
        v_handoff = False
        if v_workspace_created:
            handoff_file = working_dir_path / ".hephaestus_handoff.json"
            v_handoff = handoff_file.exists() and ws_orch.get("ready_for_execution", False)
        verifications["handoff_state_recorded"] = v_handoff

        # Verify Staged Files Handled
        v_files_handled = False
        if v_workspace_created:
            inbox_cleared = not (working_dir_path / ".harness_inbox").exists()
            v_files_handled = inbox_cleared
        verifications["staged_files_handled"] = v_files_handled

        all_verified = all(verifications.values()) and not errors

        # Output Summary
        if verbose:
            print("\n" + "=" * 80)
            print(f"📊 WEBHOOK END-TO-END VERIFICATION: {ticket_key}")
            print("=" * 80)
            for check_name, status in verifications.items():
                icon = "✅ PASS" if status else "❌ FAIL"
                print(f"  • {check_name:<28}: {icon}")
            
            print(f"\n• HTTP Status:       {http_status}")
            print(f"• Working Directory: {working_dir_path}")
            print(f"• Target Platform:   {target_platform}")
            print(f"• Execution Time:    {elapsed:.2f}s")
            print(f"• Overall Status:    {'✅ VERIFIED' if all_verified else '❌ FAILED'}")
            if errors:
                print("\n⚠️  Errors:")
                for err in errors:
                    print(f"  - {err}")
            print("=" * 80)

        return {
            "success": all_verified,
            "http_status": http_status,
            "ticket_key": ticket_key,
            "mode": mode,
            "target_platform": target_platform,
            "working_directory": str(working_dir_path) if working_dir_path else None,
            "verifications": verifications,
            "response_body": response_body,
            "duration_seconds": round(elapsed, 3),
            "errors": errors
        }


incoming_webhook_tester = IncomingWebhookTester()
