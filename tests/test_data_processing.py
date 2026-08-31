import time
import queue
import threading
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import JIRA_WEBHOOK_SECRET
from backend.watcher.webhook_watcher import (
    WebhookWatcher,
    WebhookPayloadFormatter,
    FormattedWebhookPayload,
    compute_signature
)
from backend.preprocessor.prompt_extractor import PromptExtractor
from backend.preprocessor.file_gatherer import FileGatherer
from test_harness.webhook.validator import WebhookPayloadValidator


@pytest.mark.data_processing
class TestDataProcessingStep:
    """
    Test suite specifically verifying the data processing step:
    1. Waiting and receiving incoming webhook data (via listeners, threads, and HTTP endpoints).
    2. Accurate extraction of <|prompt|>, <|prompt-new|>, and optional <|preparations|> tags.
    3. Proper stripping of tags from in-memory comments while preserving raw payload comments.
    4. Staging of prompt.md and preparations.md for Docker setup and MCP tools.
    """

    @pytest.fixture
    def validator(self):
        return WebhookPayloadValidator()

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_wait_and_receive_via_listener_queue(self, validator):
        """
        Verifies that the system can wait on an incoming data stream, receive it asynchronously,
        and accurately extract all data fields.
        """
        received_queue = queue.Queue()
        watcher = WebhookWatcher(require_secret=False)
        watcher.register_listener(lambda payload: received_queue.put(payload))

        test_payload = {
            "webhookEvent": "comment_created",
            "comment": {
                "id": "9901",
                "body": (
                    "<|prompt|> Add Redis caching for payment status queries.\n"
                    "<|preparations|> Start redis:7-alpine container and enable MCP cache tool."
                ),
                "author": {"displayName": "Dev Dave", "name": "dave"}
            },
            "issue": {
                "key": "PAY-880",
                "fields": {
                    "summary": "Optimize payment status lookup",
                    "project": {"key": "PAY"}
                }
            }
        }

        # Simulate background incoming push after slight wait delay
        def push_after_delay():
            time.sleep(0.05)
            watcher.receive_webhook(test_payload)

        thread = threading.Thread(target=push_after_delay, daemon=True)
        thread.start()

        # Step: Wait and receive the data
        start_wait = time.perf_counter()
        received_payload: FormattedWebhookPayload = received_queue.get(timeout=2.0)
        wait_duration = time.perf_counter() - start_wait
        assert wait_duration >= 0.04, "Expected realistic wait before reception"

        # Verification of extracted data
        assert isinstance(received_payload, FormattedWebhookPayload)
        assert received_payload.jira_issue_key == "PAY-880"
        assert received_payload.project_key == "PAY"
        assert received_payload.prompt_tag == "prompt"
        assert received_payload.is_ai_trigger is True
        assert received_payload.has_preparations is True
        expected_prep = "Start redis:7-alpine container and enable MCP cache tool."
        assert received_payload.preparations == expected_prep
        assert received_payload.in_memory_comment == "Add Redis caching for payment status queries."
        assert "<|preparations|>" not in received_payload.in_memory_comment
        assert "<|prompt|>" not in received_payload.in_memory_comment
        assert received_payload.raw_comment == test_payload["comment"]["body"]

        validator.validate_schema(received_payload)
        validator.validate_preparations_extraction(received_payload, expected_prep)

    def test_wait_and_receive_via_http_endpoint(self, client):
        """
        Verifies that the HTTP endpoint (/api/webhooks/jira) waits, receives,
        and returns the correctly extracted data including optional preparations.
        """
        body_str = (
            "<|prompt|> Upgrade SQLAlchemy to v2.\n"
            "<|preparations|> Install libpq-dev inside Docker container."
        )
        payload = {
            "webhookEvent": "comment_created",
            "comment": {"id": "9902", "body": body_str},
            "issue": {"key": "CORE-990", "fields": {"summary": "SQLAlchemy 2 migration", "project": {"key": "CORE"}}}
        }
        import json
        raw_bytes = json.dumps(payload).encode("utf-8")
        sig = compute_signature(raw_bytes, JIRA_WEBHOOK_SECRET)

        headers = {
            "X-Hub-Signature-256": f"sha256={sig}",
            "Content-Type": "application/json"
        }

        response = client.post("/api/webhooks/jira", content=raw_bytes, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        formatted = data["formatted"]
        assert formatted["jira_issue_key"] == "CORE-990"
        assert formatted["prompt_tag"] == "prompt"
        assert formatted["is_ai_trigger"] is True
        assert formatted["has_preparations"] is True
        assert formatted["preparations"] == "Install libpq-dev inside Docker container."
        assert formatted["in_memory_comment"] == "Upgrade SQLAlchemy to v2."

    def test_extract_inline_preparations_tag(self, validator):
        """
        Verifies extraction of single-line inline <|preparations|> tag.
        """
        comment = (
            "<|prompt|> Implement user auth refresh token rotation.\n"
            "<|preparations|> Run migrations with alembic upgrade head."
        )
        payload = WebhookPayloadFormatter.format_payload({
            "comment_text": comment,
            "jira_issue_key": "AUTH-701"
        })

        expected_prep = "Run migrations with alembic upgrade head."
        assert payload.prompt_tag == "prompt"
        assert payload.has_preparations is True
        assert payload.preparations == expected_prep
        assert payload.in_memory_comment == "Implement user auth refresh token rotation."
        assert validator.validate_preparations_extraction(payload, expected_prep)

    def test_extract_multiline_block_preparations(self, validator):
        """
        Verifies extraction of multiline <|preparations|> ... </|preparations|> block.
        Preserves internal formatting, bullets, and structure for MCP tools.
        """
        comment = (
            "<|prompt|> Build payment retry queue worker.\n"
            "<|preparations|>\n"
            "- Step 1: Start rabbitmq:3-management on port 5672\n"
            "- Step 2: Grant AI access to MCP tool 'rabbitmq_queue_inspector'\n"
            "- Step 3: Set environment variable BROKER_URL=amqp://guest:guest@localhost:5672\n"
            "</|preparations|>"
        )
        payload = WebhookPayloadFormatter.format_payload({
            "comment_text": comment,
            "jira_issue_key": "PAY-702"
        })

        expected_prep = (
            "- Step 1: Start rabbitmq:3-management on port 5672\n"
            "- Step 2: Grant AI access to MCP tool 'rabbitmq_queue_inspector'\n"
            "- Step 3: Set environment variable BROKER_URL=amqp://guest:guest@localhost:5672"
        )
        assert payload.prompt_tag == "prompt"
        assert payload.has_preparations is True
        assert payload.preparations == expected_prep
        assert payload.in_memory_comment == "Build payment retry queue worker."
        assert validator.validate_preparations_extraction(payload, expected_prep)

    def test_extract_preparations_before_prompt_new(self, validator):
        """
        Verifies extraction when <|preparations|> appears before <|prompt-new|>.
        """
        comment = (
            "<|preparations|>\n"
            "Configure Docker with python:3.12-slim and mount poetry cache.\n"
            "</|preparations|>\n"
            "<|prompt-new|> Scaffold new analytics reporting microservice."
        )
        payload = WebhookPayloadFormatter.format_payload({
            "comment_text": comment,
            "jira_issue_key": "ANALYTICS-1"
        })

        expected_prep = "Configure Docker with python:3.12-slim and mount poetry cache."
        assert payload.prompt_tag == "prompt-new"
        assert payload.is_ai_trigger is True
        assert payload.has_preparations is True
        assert payload.preparations == expected_prep
        assert payload.in_memory_comment == "Scaffold new analytics reporting microservice."
        assert validator.validate_preparations_extraction(payload, expected_prep)

    def test_extract_when_preparations_omitted(self, validator):
        """
        Verifies that when <|preparations|> is omitted, preparations defaults to None
        and has_preparations is False, while normal prompt extraction works without issue.
        """
        comment = "<|prompt|> Simple bug fix for null pointer in parser."
        payload = WebhookPayloadFormatter.format_payload({
            "comment_text": comment,
            "jira_issue_key": "BUG-101"
        })

        assert payload.prompt_tag == "prompt"
        assert payload.is_ai_trigger is True
        assert payload.has_preparations is False
        assert payload.preparations is None
        assert payload.in_memory_comment == "Simple bug fix for null pointer in parser."
        assert validator.validate_preparations_extraction(payload, None)

    def test_extract_files_with_quotes_and_spaces(self, validator):
        """
        Verifies extraction of referenced files including quoted paths with spaces.
        """
        comment = (
            "<|prompt|> Review these user profile files.\n"
            "<|files|>\n"
            "'/Users/dbearsong/Documents/User Profile - Dereck.txt'\n"
            "'/Users/dbearsong/Documents/User Profile - Dereck.docx'\n"
            "/Users/dbearsong/Documents/projects/python/job_scraper_and_analyzer/cron_debug.log\n"
            "</|files|>"
        )
        payload = WebhookPayloadFormatter.format_payload({
            "comment_text": comment,
            "jira_issue_key": "FILE-101"
        })

        expected_files = [
            "/Users/dbearsong/Documents/User Profile - Dereck.txt",
            "/Users/dbearsong/Documents/User Profile - Dereck.docx",
            "/Users/dbearsong/Documents/projects/python/job_scraper_and_analyzer/cron_debug.log"
        ]
        assert payload.prompt_tag == "prompt"
        assert payload.has_files is True
        assert payload.files == expected_files
        assert payload.prompt_instructions == "Review these user profile files."
        assert validator.validate_files_extraction(payload, expected_files)

    def test_extract_combined_prompt_preparations_and_files(self, validator):
        """
        Verifies full multi-tag extraction: prompt instructions, files, and preparations all separated cleanly.
        """
        comment = (
            "<|prompt|>\n"
            "This is the prompt message for my AI. I should be able to see this message but no prompt tag.\n\n"
            "<|files|>\n"
            "'/Users/dbearsong/Documents/User Profile - Dereck.txt'\n"
            "'/Users/dbearsong/Documents/User Profile - Dereck.docx'\n"
            "/Users/dbearsong/Documents/projects/python/job_scraper_and_analyzer/cron_debug.log\n"
            "</|files|>\n\n"
            "<|preparations|>\n"
            "Get today's date and create a text file named <date>-Update_log.txt. In this log, when completed the following details should be added to the file about the operation:\n\n"
            "* X\n"
            "* Y\n"
            "* Z\n"
            "</|preparations|>"
        )
        payload = WebhookPayloadFormatter.format_payload({
            "comment_text": comment,
            "jira_issue_key": "HEP-17"
        })

        expected_files = [
            "/Users/dbearsong/Documents/User Profile - Dereck.txt",
            "/Users/dbearsong/Documents/User Profile - Dereck.docx",
            "/Users/dbearsong/Documents/projects/python/job_scraper_and_analyzer/cron_debug.log"
        ]
        expected_prep = (
            "Get today's date and create a text file named <date>-Update_log.txt. In this log, when completed the following details should be added to the file about the operation:\n\n"
            "* X\n"
            "* Y\n"
            "* Z"
        )
        expected_prompt_clean = "This is the prompt message for my AI. I should be able to see this message but no prompt tag."

        assert payload.prompt_tag == "prompt"
        assert payload.is_ai_trigger is True
        assert payload.has_files is True
        assert payload.files == expected_files
        assert payload.has_preparations is True
        assert payload.preparations == expected_prep
        assert payload.prompt_instructions.strip() == expected_prompt_clean
        assert validator.validate_files_extraction(payload, expected_files)
        assert validator.validate_preparations_extraction(payload, expected_prep)

    def test_file_gatherer_stages_preparations_file(self):
        """
        Verifies that PromptExtractor creates preparations.md in the task staging directory,
        and FileGatherer reads/stages it and passes it along for Docker/MCP setup.
        """
        prompt_extractor = PromptExtractor()
        file_gatherer = FileGatherer()

        comment = (
            "<|prompt|> Implement search indexing.\n"
            "<|preparations|> Mount Elasticsearch MCP tool on port 9200."
        )
        task_id = "task_data_proc_test"
        ok, meta = prompt_extractor.extract_prompt(comment, task_id)
        assert ok is True
        assert meta["has_preparations"] is True
        assert meta["preparations"] == "Mount Elasticsearch MCP tool on port 9200."

        prep_path = Path(meta["preparations_file_path"])
        assert prep_path.exists(), "Expected preparations.md to be created in staging"
        assert prep_path.read_text(encoding="utf-8") == "Mount Elasticsearch MCP tool on port 9200."

        # Verify FileGatherer incorporates preparations into stage result
        stage_res = file_gatherer.extract_and_stage_files(
            meta["prompt_file_path"],
            meta["task_staging_dir"],
            preparations=meta["preparations"]
        )
        assert stage_res["has_preparations"] is True
        assert stage_res["preparations"] == "Mount Elasticsearch MCP tool on port 9200."
        assert Path(stage_res["preparations_file_path"]).exists()

    def test_pipeline_dispatch_passes_preparations(self):
        """
        Verifies that WebhookWatcher forwards both cleaned in-memory prompt and
        extracted preparations to the downstream pipeline engine.
        """
        captured_calls = []

        class MockPipelineEngine:
            def process_webhook_prompt(self, comment_text, jira_issue_key, issue_summary="", project_key_hint="", preparations=None):
                captured_calls.append({
                    "comment_text": comment_text,
                    "jira_issue_key": jira_issue_key,
                    "preparations": preparations
                })
                return {"success": True, "task_id": "task_mock"}

        mock_engine = MockPipelineEngine()
        watcher = WebhookWatcher(pipeline_engine=mock_engine, require_secret=False)

        raw_payload = {
            "webhookEvent": "comment_created",
            "comment": {
                "id": "123",
                "body": (
                    "<|prompt|> Optimize database indices.\n"
                    "<|preparations|> Run VACUUM ANALYZE before building indices."
                )
            },
            "issue": {"key": "DB-55", "fields": {"project": {"key": "DB"}}}
        }

        formatted = watcher.receive_webhook(raw_payload)
        res = watcher.dispatch_to_pipeline(formatted)

        assert res["success"] is True
        assert len(captured_calls) == 1
        call = captured_calls[0]
        assert call["jira_issue_key"] == "DB-55"
        assert call["comment_text"] == "Optimize database indices."
        assert call["preparations"] == "Run VACUUM ANALYZE before building indices."
