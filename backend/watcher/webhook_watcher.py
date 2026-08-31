import re
import uuid
import hmac
import hashlib
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, Callable, List
from pydantic import BaseModel, Field
from backend.config import JIRA_WEBHOOK_SECRET


logger = logging.getLogger("hephaestus.webhook_watcher")

PROMPT_TAG = "<|prompt|>"
PROMPT_NEW_TAG = "<|prompt-new|>"
PREPARATIONS_TAG = "<|preparations|>"
PREPARATIONS_END_TAG = "</|preparations|>"
FILES_TAG = "<|files|>"
FILES_END_TAG = "</|files|>"

class WebhookSecretVerificationError(Exception):
    """Raised when an incoming webhook fails secret or signature verification."""
    pass

class FormattedWebhookPayload(BaseModel):
    """
    Standardized payload format passed from the Webhook Watcher
    to subsequent downstream workflow and coding harness steps.
    """
    jira_issue_key: str = Field(description="Standard Jira ticket key, e.g. PROJ-101")
    project_key: str = Field(description="Project key identifier, e.g. PROJ")
    summary: str = Field(default="", description="Jira issue summary / title")
    prompt_tag: Optional[str] = Field(default=None, description="'prompt', 'prompt-new', or None")
    is_ai_trigger: bool = Field(default=False, description="True if a valid prompt tag is present")
    prompt_instructions: str = Field(default="", description="Clean AI prompt instructions with prompt, files, and preparations tags removed")
    in_memory_comment: str = Field(description="In-memory copy of comment with prompt and preparations tags stripped (retains files block for file staging)")
    raw_comment: str = Field(default="", description="Original raw comment text before stripping")
    files: List[str] = Field(default_factory=list, description="List of file paths extracted from <|files|> tag")
    has_files: bool = Field(default=False, description="True if files tag was provided")
    preparations: Optional[str] = Field(default=None, description="Optional setup / container / MCP instructions extracted from <|preparations|> tag")
    has_preparations: bool = Field(default=False, description="True if preparations tag was provided")
    author: Dict[str, Any] = Field(default_factory=dict, description="Comment author details")
    event_type: str = Field(default="custom", description="Webhook event type, e.g. comment_created, jira:issue_updated")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="ISO timestamp of receipt")
    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}", description="Unique pipeline task tracking ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context, labels, status")


def compute_signature(payload_bytes: bytes, secret: Optional[str] = None) -> str:
    """Computes HMAC-SHA256 hex digest for a payload using the configured webhook secret."""
    active_secret = secret or JIRA_WEBHOOK_SECRET or ""
    return hmac.new(active_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def verify_webhook_secret(
    payload_bytes: bytes,
    headers: Dict[str, str],
    secret: Optional[str] = None
) -> bool:
    """
    Verifies that the incoming webhook headers contain a valid secret or HMAC-SHA256 signature.
    Configured to read from .env via JIRA_WEBHOOK_SECRET.

    Supported header conventions:
    1. X-Hub-Signature or X-Hub-Signature-256: 'sha256=<hex_digest>'
    2. X-Webhook-Secret or X-Jira-Webhook-Secret: direct token comparison
    3. Authorization: 'Bearer <secret>'
    """
    configured_secret = secret or JIRA_WEBHOOK_SECRET or ""
    if not configured_secret:
        raise WebhookSecretVerificationError("Webhook secret is not configured in .env (JIRA_WEBHOOK_SECRET missing).")

    if not headers:
        return False

    # Normalize headers to lowercase
    lower_headers = {k.lower(): v for k, v in headers.items()}

    # 1. HMAC SHA-256 signature check (e.g. X-Hub-Signature-256 or X-Hub-Signature)
    sig_header = lower_headers.get("x-hub-signature-256") or lower_headers.get("x-hub-signature")
    if sig_header:
        expected_sig = compute_signature(payload_bytes, configured_secret)
        provided_sig = sig_header
        if provided_sig.startswith("sha256="):
            provided_sig = provided_sig[len("sha256="):]
        if hmac.compare_digest(provided_sig, expected_sig):
            return True

    # 2. Direct secret token header check (e.g. X-Webhook-Secret, X-Jira-Webhook-Secret)
    token_header = (
        lower_headers.get("x-webhook-secret") or
        lower_headers.get("x-jira-webhook-secret")
    )
    if token_header and hmac.compare_digest(token_header, configured_secret):
        return True

    # 3. Authorization Bearer header
    auth_header = lower_headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):].strip()
        if hmac.compare_digest(token, configured_secret):
            return True

    return False


class WebhookPayloadFormatter:
    """
    Parses and formats raw incoming webhook payloads (Jira standard or custom JSON)
    into the standardized FormattedWebhookPayload schema, extracting <|prompt|>,
    <|prompt-new|>, <|files|>, and optional <|preparations|> tags.
    """

    @staticmethod
    def extract_preparations_tag(text: str) -> Tuple[Optional[str], str]:
        """
        Extracts optional <|preparations|> tag content and returns:
        (preparations_content, text_with_preparations_stripped)

        Supports both block format:
            <|preparations|>...instructions...</|preparations|>
        and open tag format:
            <|preparations|>...instructions...(up to next tag or end of string)
        """
        if not text or PREPARATIONS_TAG not in text:
            return None, text

        # 1. Check for block tag with explicit closing tag: <|preparations|>...</|preparations|>
        block_pattern = re.compile(
            r"<\|preparations\|>(.*?)(?:<\/\|preparations\|>|<\|endpreparations\|>)",
            re.DOTALL | re.IGNORECASE
        )
        match = block_pattern.search(text)
        if match:
            prep_content = match.group(1).strip()
            remaining = text[:match.start()] + text[match.end():]
            return prep_content, remaining.strip()

        # 2. Check for open tag ending at <|prompt-new|> or <|prompt|> or <|files|> or end of text
        open_pattern = re.compile(
            r"<\|preparations\|>(.*?)(?=<\|prompt-new\|>|<\|prompt\|>|<\|files\|>|$)",
            re.DOTALL | re.IGNORECASE
        )
        match = open_pattern.search(text)
        if match:
            prep_content = match.group(1).strip()
            remaining = text[:match.start()] + text[match.end():]
            return prep_content, remaining.strip()

        return None, text

    @staticmethod
    def extract_files_tag(text: str) -> Tuple[List[str], str]:
        """
        Extracts list of file paths referenced in <|files|> tag.
        Supports both block format (<|files|>...</|files|>) and open format (<|files|>... up to next tag or end).
        Returns (files_list, text_with_files_stripped).
        """
        if not text or "<|files|>" not in text:
            return [], text

        # 1. Block tag with explicit closing tag: <|files|>...</|files|> or <|endfiles|>
        block_pattern = re.compile(
            r"<\|files\|>(.*?)(?:<\/\|files\|>|<\|endfiles\|>)",
            re.DOTALL | re.IGNORECASE
        )
        match = block_pattern.search(text)
        if match:
            files_block = match.group(1)
            remaining = text[:match.start()] + text[match.end():]
        else:
            # 2. Open tag ending at <|preparations|> or </|preparations|> or <|prompt-new|> or <|prompt|> or end of text
            open_pattern = re.compile(
                r"<\|files\|>(.*?)(?=<\|preparations\|>|<\/\|preparations\|>|<\|prompt-new\|>|<\|prompt\|>|$)",
                re.DOTALL | re.IGNORECASE
            )
            match = open_pattern.search(text)
            if match:
                files_block = match.group(1)
                remaining = text[:match.start()] + text[match.end():]
            else:
                return [], text

        raw_paths = []
        for line in files_block.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("<|") or line.startswith("</|"):
                continue
            # Check if entire line is quoted (e.g. '/path/to/file with spaces.txt')
            if (line.startswith("'") and line.endswith("'")) or (line.startswith('"') and line.endswith('"')):
                clean_p = line[1:-1].strip()
                if clean_p:
                    raw_paths.append(clean_p)
            else:
                # Comma-separated or whitespace paths
                for part in line.split(","):
                    part_clean = part.strip().strip("`\"'")
                    if part_clean and not part_clean.startswith("#") and not part_clean.startswith("<|") and not part_clean.startswith("</|"):
                        raw_paths.append(part_clean)

        return raw_paths, remaining.strip()

    @classmethod
    def extract_tags_and_content(cls, text: str) -> Tuple[Optional[str], Optional[str], List[str], str, str]:
        """
        Extracts all structured tag components from comment text:
        - prompt_tag: 'prompt', 'prompt-new', or None
        - preparations: extracted setup/container/MCP instructions, or None
        - files: list of referenced file paths, or []
        - in_memory_comment: comment with prompt and preparations tags stripped (retains files block for file gatherer)
        - prompt_instructions: pure clean prompt instructions with prompt, preparations, AND files blocks stripped
        """
        if not text:
            return None, None, [], "", ""

        # Extract optional preparations
        preparations, text_without_prep = cls.extract_preparations_tag(text)

        # Extract files
        files, text_without_prep_or_files = cls.extract_files_tag(text_without_prep)

        # Check prompt tag
        stripped_leading = text_without_prep.lstrip()
        stripped_clean = text_without_prep_or_files.lstrip()

        tag_type = None
        in_memory_copy = text_without_prep
        prompt_instructions = text_without_prep_or_files

        if stripped_leading.startswith(PROMPT_NEW_TAG):
            tag_type = "prompt-new"
            in_memory_copy = stripped_leading[len(PROMPT_NEW_TAG):].lstrip()
        elif stripped_leading.startswith(PROMPT_TAG):
            tag_type = "prompt"
            in_memory_copy = stripped_leading[len(PROMPT_TAG):].lstrip()

        if stripped_clean.startswith(PROMPT_NEW_TAG):
            prompt_instructions = stripped_clean[len(PROMPT_NEW_TAG):].lstrip()
        elif stripped_clean.startswith(PROMPT_TAG):
            prompt_instructions = stripped_clean[len(PROMPT_TAG):].lstrip()

        return tag_type, preparations, files, in_memory_copy, prompt_instructions

    @classmethod
    def identify_and_strip_prompt_tag(cls, text: str) -> Tuple[Optional[str], str]:
        """
        Identifies whether text begins with <|prompt|> or <|prompt-new|>,
        and strips the tags (including optional preparations) from the in-memory copy of the comment.
        Maintains backwards-compatible return signature: (tag_type, in_memory_comment).
        """
        tag_type, _, _, in_memory_copy, _ = cls.extract_tags_and_content(text)
        return tag_type, in_memory_copy

    @classmethod
    def format_payload(cls, raw_data: Any) -> FormattedWebhookPayload:
        """
        Extracts and normalizes Jira Cloud or direct JSON webhook payloads,
        extracting prompt tags, preparations tags, files, and metadata.
        """
        if not isinstance(raw_data, dict):
            raise ValueError(f"Invalid webhook payload: expected JSON object / dict, got {type(raw_data).__name__}")

        event_type = raw_data.get("webhookEvent") or raw_data.get("event") or "custom"
        raw_comment = ""
        issue_key = ""
        issue_summary = ""
        project_key = ""
        author: Dict[str, Any] = {}
        metadata: Dict[str, Any] = {}

        # 1. Extract from standard Jira comment payload
        if "comment" in raw_data and isinstance(raw_data["comment"], dict):
            comment_obj = raw_data["comment"]
            raw_comment = comment_obj.get("body", "") or ""
            if "author" in comment_obj and isinstance(comment_obj["author"], dict):
                author = {
                    "displayName": comment_obj["author"].get("displayName", "Unknown"),
                    "name": comment_obj["author"].get("name", "unknown"),
                    "emailAddress": comment_obj["author"].get("emailAddress", "")
                }

        # 2. Fallback: extract latest comment from issue fields if present
        if not raw_comment and "issue" in raw_data and isinstance(raw_data["issue"], dict):
            issue_obj = raw_data["issue"]
            fields = issue_obj.get("fields", {}) or {}
            comment_field = fields.get("comment", {}) or {}
            comments_list = comment_field.get("comments", []) or []
            if comments_list and isinstance(comments_list[-1], dict):
                latest = comments_list[-1]
                raw_comment = latest.get("body", "") or ""
                if "author" in latest and isinstance(latest["author"], dict):
                    author = {
                        "displayName": latest["author"].get("displayName", "Unknown"),
                        "name": latest["author"].get("name", "unknown")
                    }

        # 3. Fallback: direct JSON format
        if not raw_comment and "comment_text" in raw_data:
            raw_comment = str(raw_data.get("comment_text") or "")

        # 4. Extract issue key and fields
        if "issue" in raw_data and isinstance(raw_data["issue"], dict):
            issue_obj = raw_data["issue"]
            issue_key = issue_obj.get("key", "") or ""
            fields = issue_obj.get("fields", {}) or {}
            issue_summary = fields.get("summary", "") or ""
            labels = fields.get("labels", []) or []
            metadata["labels"] = labels
            if "project" in fields and isinstance(fields["project"], dict):
                project_key = fields["project"].get("key", "") or ""
            if "status" in fields and isinstance(fields["status"], dict):
                metadata["jira_status"] = fields["status"].get("name", "")

        # Direct fields fallback
        if not issue_key and "jira_issue_key" in raw_data:
            issue_key = str(raw_data.get("jira_issue_key") or "")
        if not issue_summary and "summary" in raw_data:
            issue_summary = str(raw_data.get("summary") or "")
        if not project_key and "project_key" in raw_data:
            project_key = str(raw_data.get("project_key") or "")

        # Derive project key from issue key if needed (e.g. "PAY-123" -> "PAY")
        if not project_key and issue_key and "-" in issue_key:
            project_key = issue_key.split("-")[0]
        elif not project_key:
            project_key = "DEFAULT"

        if not issue_key:
            issue_key = f"{project_key}-UNKNOWN"

        # Extract prompt tag, optional preparations tag, files, and clean in-memory comment
        tag_type, preparations, files, in_memory_comment, prompt_instructions = cls.extract_tags_and_content(raw_comment)
        is_ai_trigger = tag_type is not None

        return FormattedWebhookPayload(
            jira_issue_key=issue_key,
            project_key=project_key,
            summary=issue_summary,
            prompt_tag=tag_type,
            is_ai_trigger=is_ai_trigger,
            prompt_instructions=prompt_instructions,
            in_memory_comment=in_memory_comment,
            raw_comment=raw_comment,
            files=files,
            has_files=len(files) > 0,
            preparations=preparations,
            has_preparations=preparations is not None,
            author=author,
            event_type=event_type,
            metadata=metadata
        )


class WebhookWatcher:
    """
    Component that receives, logs, formats, and dispatches webhook events.
    Enforces webhook secret/signature verification configured via .env (JIRA_WEBHOOK_SECRET).
    Extracts <|prompt|>, <|prompt-new|>, <|files|>, and optional <|preparations|> tags.
    Supports plugging in simulated feeds as well as live HTTP Jira webhooks.
    """

    def __init__(
        self,
        pipeline_engine: Optional[Any] = None,
        require_secret: bool = True,
        secret: Optional[str] = None
    ):
        self.pipeline_engine = pipeline_engine
        self.require_secret = require_secret
        self.secret = secret or JIRA_WEBHOOK_SECRET
        self.listeners: List[Callable[[FormattedWebhookPayload], None]] = []
        self.received_log: List[FormattedWebhookPayload] = []
        self.total_received = 0
        self.ai_triggers_count = 0
        self.ignored_count = 0
        self.security_rejections_count = 0

    def register_listener(self, callback: Callable[[FormattedWebhookPayload], None]):
        """Register a callback for every received and formatted webhook."""
        self.listeners.append(callback)

    def verify_secret(self, payload_bytes: bytes, headers: Dict[str, str]) -> bool:
        """Verifies webhook signature/secret using the configured secret."""
        return verify_webhook_secret(payload_bytes, headers, secret=self.secret)

    def log_webhook_event(
        self,
        event_name: str,
        stage: str,
        status: str,
        details: Dict[str, Any],
        error: Optional[str] = None
    ) -> Path:
        """
        Logs incoming webhook traffic, pipeline progression, stop reasons, and extraction details
        to a dedicated structured log file with ISO timestamps in tests/test_logs/.
        """
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        root = Path(__file__).resolve().parent.parent.parent
        log_dir = root / "tests" / "test_logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        date_str = now.strftime("%Y%m%d")
        traffic_log_file = log_dir / f"webhook_traffic_{date_str}.log"

        status_emoji = "✅ SUCCESS" if status.upper() in ("SUCCESS", "PASSED", "PROCESSED") else (
            "⚠️ STOPPED/IGNORED" if status.upper() in ("STOPPED", "IGNORED") else "❌ REJECTED/FAILED"
        )

        entry = (
            f"--------------------------------------------------------------------------------\n"
            f"[{now_str}] {status_emoji} | Stage: {stage.upper()} | Event: {event_name}\n"
            f"  STATUS      : {status}\n"
        )
        for k, v in details.items():
            entry += f"  {k.upper():<12}: {repr(v) if isinstance(v, str) and len(v) < 100 else v}\n"
        if error:
            entry += f"  ERROR/STOP  : {error}\n"
        entry += f"--------------------------------------------------------------------------------\n\n"

        with open(traffic_log_file, "a", encoding="utf-8") as f:
            f.write(entry)

        return traffic_log_file

    def receive_webhook(
        self,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        raw_body: Optional[bytes] = None
    ) -> FormattedWebhookPayload:
        """
        Entrypoint for incoming webhooks.
        Enforces webhook secret verification when require_secret is True.
        Formats the payload, updates stats, logs event, notifies listeners, and returns formatted payload.
        """
        # Secret verification requirement
        if self.require_secret:
            body_bytes = raw_body or json.dumps(payload, sort_keys=True).encode("utf-8")
            valid = self.verify_secret(body_bytes, headers or {})
            if not valid:
                self.security_rejections_count += 1
                logger.warning("[WebhookWatcher] Webhook secret verification failed: missing or invalid secret/signature")
                self.log_webhook_event(
                    event_name=payload.get("webhookEvent", "unknown"),
                    stage="secret_verification",
                    status="REJECTED",
                    details={"headers": dict(headers or {})},
                    error="Webhook secret verification failed: invalid or missing signature/secret"
                )
                raise WebhookSecretVerificationError(
                    "Webhook secret verification failed: request is missing valid X-Hub-Signature or X-Webhook-Secret."
                )

        logger.info("[WebhookWatcher] Webhook secret verified successfully.")
        formatted = WebhookPayloadFormatter.format_payload(payload)

        self.total_received += 1
        if formatted.is_ai_trigger:
            self.ai_triggers_count += 1
            self.log_webhook_event(
                event_name=formatted.event_type,
                stage="reception_and_parsing",
                status="PROCESSED",
                details={
                    "jira_key": formatted.jira_issue_key,
                    "prompt_tag": formatted.prompt_tag,
                    "is_ai_trigger": True,
                    "has_preparations": formatted.has_preparations,
                    "preparations": formatted.preparations,
                    "prompt_instructions": formatted.prompt_instructions[:100],
                    "raw_comment": formatted.raw_comment[:100]
                }
            )
        else:
            self.ignored_count += 1
            self.log_webhook_event(
                event_name=formatted.event_type,
                stage="reception_and_parsing",
                status="STOPPED",
                details={
                    "jira_key": formatted.jira_issue_key,
                    "prompt_tag": None,
                    "is_ai_trigger": False,
                    "raw_comment": formatted.raw_comment[:100]
                },
                error="Stopped: Comment does not begin with <|prompt|> or <|prompt-new|>. Pipeline trigger skipped."
            )

        self.received_log.append(formatted)

        # Notify any registered listeners (e.g. test harness, monitors, websockets)
        for listener in self.listeners:
            try:
                listener(formatted)
            except Exception as e:
                logger.error("[WebhookWatcher] Listener error: %s", e)

        return formatted

    def dispatch_to_pipeline(self, formatted: FormattedWebhookPayload) -> Dict[str, Any]:
        """
        Forwards a verified AI prompt trigger payload to the downstream workflow pipeline.
        Passes both the cleaned in-memory prompt and the optional preparations instructions.
        Logs outcome and exact stop reasons if execution halts.
        """
        if not formatted.is_ai_trigger:
            reason = "Ignored: No prompt tag"
            self.log_webhook_event(
                event_name=formatted.event_type,
                stage="pipeline_dispatch",
                status="STOPPED",
                details={"jira_key": formatted.jira_issue_key},
                error=f"Stopped at dispatch gate: {reason}"
            )
            return {"success": False, "reason": reason}

        if self.pipeline_engine:
            try:
                result = self.pipeline_engine.process_webhook_prompt(
                    comment_text=formatted.in_memory_comment,
                    jira_issue_key=formatted.jira_issue_key,
                    issue_summary=formatted.summary,
                    project_key_hint=formatted.project_key,
                    preparations=formatted.preparations
                )
                success = result.get("success", True)
                status_str = "SUCCESS" if success else "FAILED"
                self.log_webhook_event(
                    event_name=formatted.event_type,
                    stage="pipeline_execution",
                    status=status_str,
                    details={
                        "jira_key": formatted.jira_issue_key,
                        "task_id": result.get("task_id", "unknown"),
                        "pipeline_result": result
                    },
                    error=result.get("error") or result.get("reason") if not success else None
                )
                return result
            except Exception as exc:
                self.log_webhook_event(
                    event_name=formatted.event_type,
                    stage="pipeline_execution",
                    status="FAILED",
                    details={"jira_key": formatted.jira_issue_key},
                    error=f"Pipeline exception: {str(exc)}"
                )
                return {"success": False, "error": str(exc)}

        self.log_webhook_event(
            event_name=formatted.event_type,
            stage="pipeline_dispatch",
            status="SUCCESS",
            details={
                "jira_key": formatted.jira_issue_key,
                "note": "Dispatched (no pipeline engine attached)"
            }
        )
        return {"success": True, "message": "Dispatched (no pipeline engine attached)", "payload": formatted.model_dump()}

    def reset_stats(self):
        """Resets in-memory metrics and logs (useful between test runs)."""
        self.total_received = 0
        self.ai_triggers_count = 0
        self.ignored_count = 0
        self.security_rejections_count = 0
        self.received_log.clear()


# Default singleton instance for application use
webhook_watcher = WebhookWatcher()

