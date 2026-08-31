import time
import pytest
from typing import Dict, Any
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import JIRA_WEBHOOK_SECRET
from backend.watcher.webhook_watcher import (
    WebhookWatcher,
    FormattedWebhookPayload,
    WebhookPayloadFormatter,
    WebhookSecretVerificationError,
    verify_webhook_secret,
    compute_signature,
)
from backend.workflows.task_graph import HephaestusWorkflowEngine
from test_harness.data.loader import TestDataLoader

# Load all 50 cases for parameterized matrix test
loader = TestDataLoader()
ALL_50_CASES = loader.get_all_cases()


class TestWebhookReception:
    """
    Independent Test Suite 1: Verify Webhooks are Received & Verified.
    - Verifies webhook secret is configured and loaded from .env.
    - Verifies webhook reception requires and validates secret/signature.
    - Verifies rejected webhooks when secret is missing or invalid.
    - Tests receipt of simulated Jira and direct webhook payloads.
    - Verifies event listener triggers and reception logging.
    - Demonstrates template where live webhooks can be plugged in for testing.
    """

    def test_webhook_secret_configured_in_env(self, test_logger):
        """Verifies that the webhook secret is properly configured and loaded from .env."""
        start = time.perf_counter()
        assert JIRA_WEBHOOK_SECRET is not None, "JIRA_WEBHOOK_SECRET must be defined"
        assert len(JIRA_WEBHOOK_SECRET) > 0, "JIRA_WEBHOOK_SECRET in .env must not be empty"
        elapsed = (time.perf_counter() - start) * 1000.0

        test_logger.log_test_case(
            case_id="SEC-001",
            category="reception",
            test_type="WEBHOOK SECRET CONFIGURATION (.ENV) TEST",
            description="Verify JIRA_WEBHOOK_SECRET is loaded from .env and non-empty",
            raw_comment="Config Check",
            detected_tag=None,
            stripped_comment="Config Check",
            passed=True,
            duration_ms=elapsed
        )

    def test_webhook_secret_verification_success(self, webhook_client, test_logger):
        """Verifies that an incoming webhook with valid secret and signature is verified and accepted."""
        start = time.perf_counter()
        payload = {
            "comment_text": "<|prompt|> Verify webhook secret authorization.",
            "jira_issue_key": "SEC-100"
        }
        # Client attaches valid auth headers matching JIRA_WEBHOOK_SECRET
        formatted = webhook_client.send_with_valid_secret(payload)
        elapsed = (time.perf_counter() - start) * 1000.0

        assert formatted.jira_issue_key == "SEC-100"
        assert formatted.is_ai_trigger is True
        assert formatted.prompt_tag == "prompt"

        test_logger.log_test_case(
            case_id="SEC-002",
            category="reception",
            test_type="WEBHOOK SECRET VERIFICATION SUCCESS",
            description="Verify webhook accepted with valid HMAC-SHA256 signature and secret from .env",
            raw_comment=payload["comment_text"],
            detected_tag="prompt",
            stripped_comment=formatted.in_memory_comment,
            passed=True,
            duration_ms=elapsed
        )

    def test_webhook_secret_verification_missing_rejected(self, webhook_client, test_logger):
        """Verifies that an incoming webhook without secrets is strictly rejected."""
        start = time.perf_counter()
        payload = {
            "comment_text": "<|prompt|> Unauthenticated webhook payload.",
            "jira_issue_key": "SEC-UNAUTH"
        }

        with pytest.raises(WebhookSecretVerificationError) as exc_info:
            webhook_client.send_without_secret(payload)

        elapsed = (time.perf_counter() - start) * 1000.0
        assert "missing valid" in str(exc_info.value).lower()

        test_logger.log_test_case(
            case_id="SEC-003",
            category="reception",
            test_type="WEBHOOK SECRET SECURITY REJECTION (MISSING SECRET)",
            description="Verify unauthenticated webhook without headers is rejected with WebhookSecretVerificationError",
            raw_comment=payload["comment_text"],
            detected_tag=None,
            stripped_comment="",
            passed=True,
            duration_ms=elapsed
        )

    def test_webhook_secret_verification_invalid_rejected(self, webhook_client, test_logger):
        """Verifies that an incoming webhook with an invalid or tampered signature is strictly rejected."""
        start = time.perf_counter()
        payload = {
            "comment_text": "<|prompt|> Tampered webhook payload.",
            "jira_issue_key": "SEC-TAMPER"
        }

        with pytest.raises(WebhookSecretVerificationError) as exc_info:
            webhook_client.send_with_invalid_secret(payload)

        elapsed = (time.perf_counter() - start) * 1000.0
        assert "verification failed" in str(exc_info.value).lower()

        test_logger.log_test_case(
            case_id="SEC-004",
            category="reception",
            test_type="WEBHOOK SECRET SECURITY REJECTION (INVALID SECRET)",
            description="Verify webhook with tampered HMAC signature is rejected with WebhookSecretVerificationError",
            raw_comment=payload["comment_text"],
            detected_tag=None,
            stripped_comment="",
            passed=True,
            duration_ms=elapsed
        )

    def test_simulated_jira_comment_reception(self, webhook_client, test_logger):
        """Verifies simulated Jira comment webhook is received and recorded."""
        start = time.perf_counter()
        raw_comment = "<|prompt|> Add database index on users.email column."
        payload = webhook_client.send_jira_comment(
            comment_text=raw_comment,
            issue_key="PAY-101",
            author_name="sam.dev",
            summary="Payment user email lookup index"
        )
        elapsed = (time.perf_counter() - start) * 1000.0

        assert payload is not None
        assert payload.jira_issue_key == "PAY-101"
        assert payload.project_key == "PAY"
        assert webhook_client.total_dispatched >= 1

        test_logger.log_test_case(
            case_id="REC-001",
            category="reception",
            test_type="WEBHOOK RECEPTION & DELIVERY TEST",
            description="Simulated Jira comment webhook reception",
            raw_comment=raw_comment,
            detected_tag=payload.prompt_tag,
            stripped_comment=payload.in_memory_comment,
            passed=True,
            duration_ms=elapsed
        )

    def test_simulated_issue_updated_reception(self, webhook_client, test_logger):
        """Verifies simulated Jira issue_updated webhook with nested comment is received."""
        start = time.perf_counter()
        raw_comment = "<|prompt-new|> Bootstrap notification worker microservice."
        payload = webhook_client.send_jira_issue_update(
            comment_text=raw_comment,
            issue_key="NOTIF-202",
            summary="Scaffold Notification Worker"
        )
        elapsed = (time.perf_counter() - start) * 1000.0

        assert payload.jira_issue_key == "NOTIF-202"
        assert payload.project_key == "NOTIF"
        assert payload.prompt_tag == "prompt-new"

        test_logger.log_test_case(
            case_id="REC-002",
            category="reception",
            test_type="WEBHOOK RECEPTION & DELIVERY TEST",
            description="Simulated Jira issue_updated webhook reception",
            raw_comment=raw_comment,
            detected_tag=payload.prompt_tag,
            stripped_comment=payload.in_memory_comment,
            passed=True,
            duration_ms=elapsed
        )

    def test_webhook_watcher_listener_callback(self, webhook_client, test_logger):
        """Verifies registered listeners are called immediately upon webhook reception."""
        start = time.perf_counter()
        watcher = WebhookWatcher(secret=JIRA_WEBHOOK_SECRET)
        received_events = []

        def sample_listener(payload: FormattedWebhookPayload):
            received_events.append(payload)

        watcher.register_listener(sample_listener)

        raw_payload = {
            "webhookEvent": "comment_created",
            "comment": {"body": "<|prompt|> Fix CSS layout bug."},
            "issue": {"key": "UI-301", "fields": {"project": {"key": "UI"}}}
        }
        headers = webhook_client.create_auth_headers(raw_payload)
        watcher.receive_webhook(raw_payload, headers=headers)
        elapsed = (time.perf_counter() - start) * 1000.0

        assert len(received_events) == 1
        assert received_events[0].jira_issue_key == "UI-301"
        assert received_events[0].prompt_tag == "prompt"

        test_logger.log_test_case(
            case_id="REC-003",
            category="reception",
            test_type="WEBHOOK WATCHER LISTENER CALLBACK TEST",
            description="In-memory observer listener callback on webhook receipt",
            raw_comment=raw_payload["comment"]["body"],
            detected_tag="prompt",
            stripped_comment=received_events[0].in_memory_comment,
            passed=True,
            duration_ms=elapsed
        )

    def test_live_webhook_template_with_http_client(self, live_webhook_template, test_logger):
        """
        Template for Live Webhook Ingestion with Secret Enforcement:
        Demonstrates plugging live webhooks into an HTTP endpoint using TestClient.
        Verifies:
        1. Request with missing secret headers is rejected with 401 Unauthorized.
        2. Request with invalid HMAC signature is rejected with 401 Unauthorized.
        3. Request with valid secret/signature from .env is accepted with 200 OK.
        """
        start = time.perf_counter()
        client = TestClient(app)

        test_payload = {
            "webhookEvent": "comment_created",
            "comment": {
                "id": "9999",
                "body": "<|prompt|> Live webhook template delivery verification.",
                "author": {"displayName": "Jira Automation", "name": "jira_bot"}
            },
            "issue": {
                "key": "LIVE-888",
                "fields": {
                    "summary": "Live Webhook Test",
                    "project": {"key": "LIVE"}
                }
            }
        }

        # 1. Negative Test: missing auth headers -> rejected 401
        res_missing = client.post("/api/webhooks/jira", json=test_payload)
        assert res_missing.status_code == 401, f"Expected 401 for missing secret, got {res_missing.status_code}"

        # 2. Negative Test: tampered signature -> rejected 401
        res_invalid = client.post(
            "/api/webhooks/jira",
            json=test_payload,
            headers={"X-Hub-Signature-256": "sha256=invalidhex000000000000000000000000"}
        )
        assert res_invalid.status_code == 401, f"Expected 401 for invalid signature, got {res_invalid.status_code}"

        # 3. Positive Test: valid HMAC signature computed from .env secret -> accepted 200
        live_res = live_webhook_template.dispatch_live_webhook(test_payload, client=client)
        elapsed = (time.perf_counter() - start) * 1000.0

        assert live_res["status_code"] == 200, f"Expected 200 for valid secret, got {live_res['status_code']}"
        res_json = live_res["json"]
        assert res_json["success"] is True
        assert res_json["formatted"]["jira_issue_key"] == "LIVE-888"
        assert res_json["formatted"]["prompt_tag"] == "prompt"
        assert res_json["formatted"]["in_memory_comment"] == "Live webhook template delivery verification."

        test_logger.log_test_case(
            case_id="REC-LIVE-001",
            category="live_template",
            test_type="LIVE WEBHOOK TEMPLATE ADAPTER TEST (SECRET VERIFIED)",
            description="Live webhook template adapter dispatch with strict HMAC-SHA256 signature verification from .env",
            raw_comment=test_payload["comment"]["body"],
            detected_tag="prompt",
            stripped_comment=res_json["formatted"]["in_memory_comment"],
            passed=True,
            duration_ms=elapsed
        )


class TestPayloadFormattingAndTags:
    """
    Independent Test Suite 2: Verify Received Payloads are Correctly Formatted for Next Steps.
    Provides complete details on required data formatting schema.
    Specifically tests:
    - Identifying between comments with <|prompt|>, <|prompt-new|>, and no prompt tags.
    - Stripping <|prompt|> and <|prompt-new|> from in-memory copy of comment.
    """

    def test_formatted_data_specification_details(self, payload_validator, test_logger):
        """
        DETAILS ON HOW DATA SHOULD BE FORMATTED WHEN RECEIVED FOR NEXT STEPS:
        --------------------------------------------------------------------
        1. jira_issue_key (str)     : Jira issue key formatted as 'PROJECT-123'.
        2. project_key (str)        : Extracted project code, e.g. 'PAY'.
        3. summary (str)            : Jira issue summary / description title.
        4. prompt_tag (str|None)    : Exactly 'prompt', 'prompt-new', or None.
        5. is_ai_trigger (bool)     : True if prompt_tag is not None.
        6. in_memory_comment (str)  : Clean copy of the comment with leading prompt tag stripped.
        7. raw_comment (str)        : Immutable record of the original raw comment text.
        8. author (dict)            : Author metadata (displayName, name, emailAddress).
        9. event_type (str)         : Event category (e.g. comment_created, jira:issue_updated).
        10. timestamp (str)         : ISO 8601 UTC timestamp of webhook receipt.
        11. task_id (str)           : Generated unique task tracking ID (task_xxxxxxxx).
        12. metadata (dict)         : Contextual labels, ticket status, and issue attributes.
        """
        start = time.perf_counter()
        raw = {
            "comment_text": "<|prompt|> Refactor authentication middleware.",
            "jira_issue_key": "AUTH-100",
            "summary": "Auth middleware cleanup",
            "project_key": "AUTH"
        }
        formatted = WebhookPayloadFormatter.format_payload(raw)
        elapsed = (time.perf_counter() - start) * 1000.0

        # Validate schema contract
        assert payload_validator.validate_schema(formatted)
        assert formatted.jira_issue_key == "AUTH-100"
        assert formatted.project_key == "AUTH"
        assert formatted.summary == "Auth middleware cleanup"
        assert formatted.prompt_tag == "prompt"
        assert formatted.is_ai_trigger is True
        assert formatted.in_memory_comment == "Refactor authentication middleware."
        assert formatted.raw_comment == "<|prompt|> Refactor authentication middleware."
        assert formatted.task_id.startswith("task_")

        test_logger.log_test_case(
            case_id="FMT-001",
            category="formatting",
            test_type="PAYLOAD FORMATTING & SCHEMA SPECIFICATION TEST",
            description="Payload schema standardization for downstream pipeline execution",
            raw_comment=raw["comment_text"],
            detected_tag=formatted.prompt_tag,
            stripped_comment=formatted.in_memory_comment,
            passed=True,
            duration_ms=elapsed
        )

    def test_identify_prompt_tag(self, payload_validator, test_logger):
        """Verify identification of <|prompt|> tag and in-memory stripping."""
        start = time.perf_counter()
        raw_text = "<|prompt|> Implement Stripe webhook signature validation."
        tag_type, in_mem = WebhookPayloadFormatter.identify_and_strip_prompt_tag(raw_text)
        elapsed = (time.perf_counter() - start) * 1000.0

        assert tag_type == "prompt"
        assert in_mem == "Implement Stripe webhook signature validation."
        assert not in_mem.startswith("<|prompt|>")

        test_logger.log_test_case(
            case_id="FMT-002",
            category="formatting",
            test_type="TAG IDENTIFICATION (<|prompt|>)",
            description="Identify <|prompt|> tag and verify in-memory strip",
            raw_comment=raw_text,
            detected_tag=tag_type,
            stripped_comment=in_mem,
            passed=True,
            duration_ms=elapsed
        )

    def test_identify_prompt_new_tag(self, payload_validator, test_logger):
        """Verify identification of <|prompt-new|> tag and in-memory stripping."""
        start = time.perf_counter()
        raw_text = "<|prompt-new|> Initialize greenfield payment gateway repo."
        tag_type, in_mem = WebhookPayloadFormatter.identify_and_strip_prompt_tag(raw_text)
        elapsed = (time.perf_counter() - start) * 1000.0

        assert tag_type == "prompt-new"
        assert in_mem == "Initialize greenfield payment gateway repo."
        assert not in_mem.startswith("<|prompt-new|>")

        test_logger.log_test_case(
            case_id="FMT-003",
            category="formatting",
            test_type="TAG IDENTIFICATION (<|prompt-new|>)",
            description="Identify <|prompt-new|> tag and verify in-memory strip",
            raw_comment=raw_text,
            detected_tag=tag_type,
            stripped_comment=in_mem,
            passed=True,
            duration_ms=elapsed
        )

    def test_identify_no_prompt_tag(self, payload_validator, test_logger):
        """Verify comment without prompt tags is identified with prompt_tag=None and preserved."""
        start = time.perf_counter()
        raw_text = "Good job on the PR, merging this afternoon!"
        tag_type, in_mem = WebhookPayloadFormatter.identify_and_strip_prompt_tag(raw_text)
        elapsed = (time.perf_counter() - start) * 1000.0

        assert tag_type is None
        assert in_mem == raw_text  # in-memory copy preserved unaltered

        test_logger.log_test_case(
            case_id="FMT-004",
            category="formatting",
            test_type="TAG IDENTIFICATION (NO PROMPT TAG)",
            description="Identify comments without tags (preserved in-memory, no AI trigger)",
            raw_comment=raw_text,
            detected_tag=tag_type,
            stripped_comment=in_mem,
            passed=True,
            duration_ms=elapsed
        )

    def test_in_memory_copy_is_stripped_and_raw_is_preserved(self, payload_validator, test_logger):
        """
        Verify that in-memory copy strips the tag while raw_comment maintains the original string.
        """
        start = time.perf_counter()
        raw_text = "<|prompt|>   Format logs as structured JSON."
        payload = WebhookPayloadFormatter.format_payload({
            "comment_text": raw_text,
            "jira_issue_key": "LOG-1"
        })
        elapsed = (time.perf_counter() - start) * 1000.0

        assert payload.prompt_tag == "prompt"
        assert payload.raw_comment == raw_text
        assert payload.in_memory_comment == "Format logs as structured JSON."
        assert not payload.in_memory_comment.startswith("<|prompt|>")
        assert payload_validator.validate_tag_stripped_in_memory(payload, raw_text)

        test_logger.log_test_case(
            case_id="FMT-005",
            category="formatting",
            test_type="IN-MEMORY TAG STRIPPING VERIFICATION",
            description="Verify immutable raw_comment vs stripped in_memory_comment",
            raw_comment=raw_text,
            detected_tag=payload.prompt_tag,
            stripped_comment=payload.in_memory_comment,
            passed=True,
            duration_ms=elapsed
        )

    def test_extract_optional_preparations_tag_inline(self, payload_validator, test_logger):
        """Verify extraction of optional inline <|preparations|> tag and stripping from in-memory copy."""
        start = time.perf_counter()
        raw_text = (
            "<|prompt|> Refactor user session handling.\n"
            "<|preparations|> Ensure postgres test database container is running on port 5432 and seed test users."
        )
        payload = WebhookPayloadFormatter.format_payload({
            "comment_text": raw_text,
            "jira_issue_key": "PREP-101"
        })
        elapsed = (time.perf_counter() - start) * 1000.0

        assert payload.prompt_tag == "prompt"
        assert payload.is_ai_trigger is True
        assert payload.has_preparations is True
        expected_prep = "Ensure postgres test database container is running on port 5432 and seed test users."
        assert payload.preparations == expected_prep
        assert payload.in_memory_comment == "Refactor user session handling."
        assert "<|preparations|>" not in payload.in_memory_comment
        assert payload_validator.validate_preparations_extraction(payload, expected_prep)

        test_logger.log_test_case(
            case_id="FMT-006",
            category="formatting",
            test_type="PREPARATIONS TAG EXTRACTION (INLINE)",
            description="Verify inline <|preparations|> extracted and stripped from in-memory comment",
            raw_comment=raw_text,
            detected_tag=payload.prompt_tag,
            stripped_comment=payload.in_memory_comment,
            passed=True,
            duration_ms=elapsed,
            preparations=payload.preparations
        )

    def test_extract_optional_preparations_tag_block(self, payload_validator, test_logger):
        """Verify extraction of multiline block <|preparations|> ... </|preparations|> tag."""
        start = time.perf_counter()
        raw_text = (
            "<|prompt|> Build automated regression suite.\n"
            "<|preparations|>\n"
            "- Start Redis container cache service\n"
            "- Set MCP_POSTGRES_INSPECTOR=enabled\n"
            "- Pre-install uv and pytest packages\n"
            "</|preparations|>"
        )
        payload = WebhookPayloadFormatter.format_payload({
            "comment_text": raw_text,
            "jira_issue_key": "PREP-102"
        })
        elapsed = (time.perf_counter() - start) * 1000.0

        assert payload.prompt_tag == "prompt"
        assert payload.has_preparations is True
        expected_prep = (
            "- Start Redis container cache service\n"
            "- Set MCP_POSTGRES_INSPECTOR=enabled\n"
            "- Pre-install uv and pytest packages"
        )
        assert payload.preparations == expected_prep
        assert payload.in_memory_comment == "Build automated regression suite."
        assert payload_validator.validate_preparations_extraction(payload, expected_prep)

        test_logger.log_test_case(
            case_id="FMT-007",
            category="formatting",
            test_type="PREPARATIONS TAG EXTRACTION (MULTILINE BLOCK)",
            description="Verify multiline <|preparations|> block extracted for MCP setup",
            raw_comment=raw_text,
            detected_tag=payload.prompt_tag,
            stripped_comment=payload.in_memory_comment,
            passed=True,
            duration_ms=elapsed,
            preparations=payload.preparations
        )

    def test_extract_preparations_with_prompt_new(self, payload_validator, test_logger):
        """Verify extraction of <|preparations|> when combined with <|prompt-new|>."""
        start = time.perf_counter()
        raw_text = (
            "<|preparations|> Pull python:3.12-slim base image and initialize MCP tools.\n"
            "<|prompt-new|> Bootstrap payment gateway service with FastAPI."
        )
        payload = WebhookPayloadFormatter.format_payload({
            "comment_text": raw_text,
            "jira_issue_key": "PREP-103"
        })
        elapsed = (time.perf_counter() - start) * 1000.0

        assert payload.prompt_tag == "prompt-new"
        assert payload.is_ai_trigger is True
        assert payload.has_preparations is True
        expected_prep = "Pull python:3.12-slim base image and initialize MCP tools."
        assert payload.preparations == expected_prep
        assert payload.in_memory_comment == "Bootstrap payment gateway service with FastAPI."
        assert payload_validator.validate_preparations_extraction(payload, expected_prep)

        test_logger.log_test_case(
            case_id="FMT-008",
            category="formatting",
            test_type="PREPARATIONS WITH PROMPT-NEW",
            description="Verify <|preparations|> extracted when placed before <|prompt-new|>",
            raw_comment=raw_text,
            detected_tag=payload.prompt_tag,
            stripped_comment=payload.in_memory_comment,
            passed=True,
            duration_ms=elapsed,
            preparations=payload.preparations
        )

    def test_extract_preparations_absent_defaults_to_none(self, payload_validator, test_logger):
        """Verify that when no <|preparations|> tag is present, preparations is None and has_preparations is False."""
        start = time.perf_counter()
        raw_text = "<|prompt|> Standard prompt without preparations."
        payload = WebhookPayloadFormatter.format_payload({
            "comment_text": raw_text,
            "jira_issue_key": "PREP-104"
        })
        elapsed = (time.perf_counter() - start) * 1000.0

        assert payload.prompt_tag == "prompt"
        assert payload.preparations is None
        assert payload.has_preparations is False
        assert payload.in_memory_comment == "Standard prompt without preparations."
        assert payload_validator.validate_preparations_extraction(payload, None)

        test_logger.log_test_case(
            case_id="FMT-009",
            category="formatting",
            test_type="PREPARATIONS OMITTED (DEFAULT NONE)",
            description="Verify preparations defaults to None when tag is omitted",
            raw_comment=raw_text,
            detected_tag=payload.prompt_tag,
            stripped_comment=payload.in_memory_comment,
            passed=True,
            duration_ms=elapsed,
            preparations=None
        )


class TestWebhookWatcher50Cases:
    """
    Independent Test Suite 3: 50-Case Matrix.
    Executes all 50 test cases:
    - 80% Normal Cases (40 cases)
    - 10% Edge Cases under Normal Situations (5 cases)
    - 10% Edge Cases over Normal Situations (5 cases)
    Asserts tag identification, in-memory stripping, schema validity, and outputs execution logs.
    """

    @pytest.mark.parametrize("case", ALL_50_CASES, ids=[c["id"] for c in ALL_50_CASES])
    def test_case_execution(self, case: Dict[str, Any], webhook_client, payload_validator, test_logger):
        start = time.perf_counter()
        case_id = case["id"]
        category = case["category"]
        desc = case["description"]
        raw_payload = case["payload"]

        # Map to explicit human-readable test type for clear display
        if category == "normal":
            test_type = "NORMAL CASE (80% OF SUITE)"
        elif category == "edge_under":
            test_type = "EDGE CASE - UNDER NORMAL SITUATIONS (10% OF SUITE)"
        elif category == "edge_over":
            test_type = "EDGE CASE - OVER NORMAL SITUATIONS (10% OF SUITE)"
        else:
            test_type = category.upper()

        # 1. Dispatch through client (with secret headers automatically computed)
        formatted = webhook_client.send_raw_payload(raw_payload)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        try:
            # 2. Validate schema
            payload_validator.validate_schema(formatted)

            # 3. Validate tag identification
            expected_tag = case.get("expected_tag")
            payload_validator.validate_tag_identification(formatted, expected_tag)

            # 4. Validate AI trigger status
            expected_ai = case.get("expected_is_ai_trigger")
            assert formatted.is_ai_trigger == expected_ai, (
                f"Case {case_id}: expected is_ai_trigger={expected_ai}, got {formatted.is_ai_trigger}"
            )

            # 5. Validate in-memory comment stripping
            expected_stripped = case.get("expected_stripped_comment")
            assert formatted.in_memory_comment == expected_stripped, (
                f"Case {case_id}: stripped in-memory mismatch.\n"
                f"Expected: {repr(expected_stripped)}\n"
                f"Got     : {repr(formatted.in_memory_comment)}"
            )

            # Ensure prompt tags are never present in in_memory_comment when trigger is identified
            if expected_tag is not None:
                assert not formatted.in_memory_comment.startswith("<|prompt|>")
                assert not formatted.in_memory_comment.startswith("<|prompt-new|>")

            # 6. Validate issue key
            expected_ikey = case.get("expected_issue_key")
            assert formatted.jira_issue_key == expected_ikey, (
                f"Case {case_id}: expected issue_key={expected_ikey}, got {formatted.jira_issue_key}"
            )

            # 7. Validate preparations tag extraction
            expected_prep = case.get("expected_preparations")
            payload_validator.validate_preparations_extraction(formatted, expected_prep)

            # 8. Log success with clearly displayed test type and preparations
            test_logger.log_test_case(
                case_id=case_id,
                category=category,
                test_type=test_type,
                description=desc,
                raw_comment=formatted.raw_comment,
                detected_tag=formatted.prompt_tag,
                stripped_comment=formatted.in_memory_comment,
                passed=True,
                duration_ms=elapsed_ms,
                preparations=formatted.preparations
            )

        except Exception as exc:
            # Log failure with clearly displayed test type
            test_logger.log_test_case(
                case_id=case_id,
                category=category,
                test_type=test_type,
                description=desc,
                raw_comment=formatted.raw_comment if 'formatted' in locals() else "",
                detected_tag=formatted.prompt_tag if 'formatted' in locals() else None,
                stripped_comment=formatted.in_memory_comment if 'formatted' in locals() else "",
                passed=False,
                duration_ms=elapsed_ms,
                error_msg=str(exc)
            )
            raise


class TestAIHarnessPluggability:
    """
    Independent Test Suite 4: Verify Base Code Restructuring & AI Portion Virtualization.
    Verifies that AI stubs, mocks, and service virtualizations can be plugged
    into the restructured base code workflow engine.
    """

    def test_ai_stub_plugged_in(self, test_harness, test_logger):
        """Plugs in AI stub and verifies workflow engine executes with canned response."""
        start = time.perf_counter()
        stub = test_harness.plug_in_ai_stub(
            status="completed",
            summary="[STUB] High performance cache implemented."
        )

        engine = HephaestusWorkflowEngine(harness=stub)
        assert engine.harness == stub

        res = stub.run_task(
            prompt="Cache optimization",
            container_info={"container_name": "test_container"},
            project_config={"key": "CACHE", "name": "Cache Service"}
        )
        elapsed = (time.perf_counter() - start) * 1000.0

        assert res.status == "completed"
        assert "[STUB]" in res.summary_changes
        test_harness.unplug_ai()

        test_logger.log_test_case(
            case_id="AI-001",
            category="ai_pluggability",
            test_type="AI COMPONENT: STUB PLUGGABILITY",
            description="Verify pluggable AIStubHarness canned response inside workflow engine",
            raw_comment="Cache optimization",
            detected_tag=None,
            stripped_comment="Cache optimization",
            passed=True,
            duration_ms=elapsed
        )

    def test_ai_mock_plugged_in_and_assertions(self, test_harness, test_logger):
        """Plugs in AI mock and verifies interaction recording and assertion helpers."""
        start = time.perf_counter()
        mock = test_harness.plug_in_ai_mock()
        engine = HephaestusWorkflowEngine(harness=mock)

        engine.harness.run_task(
            prompt="Refactor database session pooling for high concurrency",
            container_info={"container_name": "db_container"},
            project_config={"key": "DB", "name": "Database Service"}
        )

        mock.assert_called(1)
        mock.assert_prompt_contains("database session pooling")
        assert mock.last_call()["project_config"]["key"] == "DB"
        elapsed = (time.perf_counter() - start) * 1000.0
        test_harness.unplug_ai()

        test_logger.log_test_case(
            case_id="AI-002",
            category="ai_pluggability",
            test_type="AI COMPONENT: MOCK PLUGGABILITY & ASSERTIONS",
            description="Verify AIMockHarness interaction tracking and verification assertions",
            raw_comment="Refactor database session pooling for high concurrency",
            detected_tag=None,
            stripped_comment="Refactor database session pooling for high concurrency",
            passed=True,
            duration_ms=elapsed
        )

    def test_ai_service_virtualizer_security_boundary(self, test_harness, test_logger):
        """Plugs in AI service virtualizer and verifies simulated security boundary pause."""
        start = time.perf_counter()
        virtualizer = test_harness.plug_in_ai_virtualizer()

        # Prompt with unapproved external domain
        prompt = "Connect to https://unapproved-api.external.com to download sensitive keys."
        res = virtualizer.run_task(
            prompt=prompt,
            container_info={"container_name": "sandbox_sec"},
            project_config={"key": "SEC", "name": "Security Service"}
        )
        elapsed = (time.perf_counter() - start) * 1000.0

        assert res.status == "paused_waiting_input"
        assert res.paused_reason == "external_access_requested"
        assert "unapproved-api.external.com" in res.question_for_user
        test_harness.unplug_ai()

        test_logger.log_test_case(
            case_id="AI-003",
            category="ai_pluggability",
            test_type="AI COMPONENT: SERVICE VIRTUALIZATION (SECURITY BOUNDARY)",
            description="Verify AIServiceVirtualizer external domain security boundary pause",
            raw_comment=prompt,
            detected_tag=None,
            stripped_comment=prompt,
            passed=True,
            duration_ms=elapsed
        )

    def test_ai_service_virtualizer_clarification_question(self, test_harness, test_logger):
        """Plugs in AI service virtualizer and verifies simulated user clarification pause."""
        start = time.perf_counter()
        virtualizer = test_harness.plug_in_ai_virtualizer()

        # Prompt with ambiguous question
        prompt = "How would you prefer we handle customer billing refunds?"
        res = virtualizer.run_task(
            prompt=prompt,
            container_info={"container_name": "sandbox_bill"},
            project_config={"key": "BILL", "name": "Billing Service"}
        )
        elapsed = (time.perf_counter() - start) * 1000.0

        assert res.status == "paused_waiting_input"
        assert res.paused_reason == "question"
        assert "[Virtual AI Clarification]" in res.question_for_user
        test_harness.unplug_ai()

        test_logger.log_test_case(
            case_id="AI-004",
            category="ai_pluggability",
            test_type="AI COMPONENT: SERVICE VIRTUALIZATION (CLARIFICATION)",
            description="Verify AIServiceVirtualizer user clarification question pause",
            raw_comment=prompt,
            detected_tag=None,
            stripped_comment=prompt,
            passed=True,
            duration_ms=elapsed
        )
