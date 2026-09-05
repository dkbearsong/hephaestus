import time
import json
from typing import Dict, Any, Optional, List
from backend.config import JIRA_WEBHOOK_SECRET
from backend.watcher.webhook_watcher import (
    WebhookWatcher,
    FormattedWebhookPayload,
    compute_signature,
    webhook_watcher as default_watcher,
)
from test_harness.base import BaseTestComponent, ComponentStatus

class WebhookWatcherClient(BaseTestComponent):
    """
    Test client for dispatching simulated webhooks to the WebhookWatcher component.
    Automatically generates authentication headers using JIRA_WEBHOOK_SECRET from .env,
    and supports sending invalid/missing secrets to verify security rejection.
    """

    def __init__(
        self,
        watcher: Optional[WebhookWatcher] = None,
        secret: Optional[str] = None,
        name: str = "webhook_client"
    ):
        super().__init__(name=name)
        self.watcher = watcher or default_watcher
        self.secret = secret or JIRA_WEBHOOK_SECRET
        self.history: List[Dict[str, Any]] = []
        self.status = ComponentStatus.ACTIVE

    def create_auth_headers(
        self,
        payload: Dict[str, Any],
        secret: Optional[str] = None,
        tamper_sig: bool = False
    ) -> Dict[str, str]:
        """Generates standard authentication headers matching .env configured secret."""
        active_secret = secret or self.secret or ""
        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        sig = compute_signature(payload_bytes, active_secret)
        if tamper_sig:
            sig = "tampered_" + sig[:-9]

        return {
            "X-Hub-Signature-256": f"sha256={sig}",
            "X-Webhook-Secret": active_secret,
            "Content-Type": "application/json"
        }

    def send_raw_payload(
        self,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        attach_default_auth: bool = True
    ) -> FormattedWebhookPayload:
        """
        Sends an arbitrary raw webhook payload to the watcher.
        Automatically attaches valid authentication headers by default unless specified.
        """
        start_time = time.perf_counter()
        raw_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")

        final_headers = {}
        if attach_default_auth:
            final_headers = self.create_auth_headers(payload)
        if headers is not None:
            final_headers.update(headers)

        formatted = self.watcher.receive_webhook(payload, headers=final_headers, raw_body=raw_bytes)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        self.history.append({
            "timestamp": time.time(),
            "raw_payload": payload,
            "headers": final_headers,
            "formatted_result": formatted,
            "elapsed_ms": elapsed_ms
        })
        return formatted

    def send_with_valid_secret(
        self,
        payload: Dict[str, Any],
        custom_secret: Optional[str] = None
    ) -> FormattedWebhookPayload:
        """Explicitly dispatches with valid secret headers."""
        headers = self.create_auth_headers(payload, secret=custom_secret)
        return self.send_raw_payload(payload, headers=headers, attach_default_auth=False)

    def send_with_invalid_secret(self, payload: Dict[str, Any]) -> FormattedWebhookPayload:
        """Dispatches with an invalid secret to verify rejection."""
        headers = self.create_auth_headers(payload, secret="invalid_secret_key_999", tamper_sig=True)
        return self.send_raw_payload(payload, headers=headers, attach_default_auth=False)

    def send_without_secret(self, payload: Dict[str, Any]) -> FormattedWebhookPayload:
        """Dispatches with zero authentication headers to verify rejection."""
        return self.send_raw_payload(payload, headers={}, attach_default_auth=False)

    def send_jira_comment(
        self,
        comment_text: str,
        issue_key: str = "TEST-101",
        author_name: str = "jane.dev",
        summary: str = "Test Jira Issue",
        project_key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> FormattedWebhookPayload:
        """Simulates a standard Jira Cloud comment_created webhook payload."""
        proj = project_key or issue_key.split("-")[0]
        payload = {
            "webhookEvent": "comment_created",
            "timestamp": int(time.time() * 1000),
            "comment": {
                "id": "10001",
                "body": comment_text,
                "author": {
                    "displayName": "Jane Developer",
                    "name": author_name,
                    "emailAddress": f"{author_name}@example.com"
                },
                "created": "2026-08-29T10:00:00.000+0000"
            },
            "issue": {
                "id": "20002",
                "key": issue_key,
                "fields": {
                    "summary": summary,
                    "project": {
                        "key": proj,
                        "name": f"Project {proj}"
                    },
                    "labels": ["run_ai_orchestrator"],
                    "status": {"name": "In Progress"}
                }
            }
        }
        return self.send_raw_payload(payload, headers=headers)

    def send_jira_issue_update(
        self,
        comment_text: str,
        issue_key: str = "TEST-102",
        summary: str = "Updated Jira Issue",
        project_key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> FormattedWebhookPayload:
        """Simulates a Jira issue_updated webhook event with comment nested in fields."""
        proj = project_key or issue_key.split("-")[0]
        payload = {
            "webhookEvent": "jira:issue_updated",
            "issue": {
                "key": issue_key,
                "fields": {
                    "summary": summary,
                    "project": {"key": proj},
                    "comment": {
                        "comments": [
                            {
                                "id": "10002",
                                "body": comment_text,
                                "author": {"displayName": "Alex Lead", "name": "alex"}
                            }
                        ]
                    }
                }
            }
        }
        return self.send_raw_payload(payload, headers=headers)

    def send_direct_payload(
        self,
        comment_text: str,
        issue_key: str = "DIRECT-100",
        summary: str = "Direct Payload Issue",
        project_key: str = "DIRECT",
        headers: Optional[Dict[str, str]] = None
    ) -> FormattedWebhookPayload:
        """Simulates a direct JSON payload (e.g. from internal scripts or gateways)."""
        payload = {
            "comment_text": comment_text,
            "jira_issue_key": issue_key,
            "summary": summary,
            "project_key": project_key
        }
        return self.send_raw_payload(payload, headers=headers)

    @property
    def total_dispatched(self) -> int:
        return len(self.history)

    def last_dispatch(self) -> Optional[Dict[str, Any]]:
        return self.history[-1] if self.history else None

    def reset(self):
        self.history.clear()
        self.watcher.reset_stats()
