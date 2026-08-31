import os
import json
import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import ROOT_DIR, get_prompt_output_dir
from backend.preprocessor.prompt_extractor import PromptExtractor
from backend.preprocessor.md_file_writer import MDFileWriter
from backend.watcher.webhook_watcher import WebhookWatcher, WebhookPayloadFormatter
from test_harness.manager import test_harness_manager
from test_harness.reporters.file_logger import TestExecutionLogger

TEST_DATA_PATH = ROOT_DIR / "test" / "test_data" / "md_file_writer_cases.json"

@pytest.fixture(scope="module")
def md_cases():
    with open(TEST_DATA_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)
    return {c["id"]: c for c in cases}

@pytest.fixture(scope="module")
def md_logger():
    logger = TestExecutionLogger()
    run_id = logger.start_new_run(prefix="md_file_writer")
    yield logger
    logger.write_summary_report()

@pytest.fixture
def client():
    return TestClient(app)

class TestMDFileWriterSuite:
    """
    Independent tests for the MD file writer, save locations, webhook pipeline trigger gating,
    and manual Jira testing route.
    """

    def test_webhook_pushed_only_if_comment_begins_with_prompt(self, md_cases, md_logger):
        """
        Requirement 1: Verify that when a webhook is received, it is pushed through the
        pipeline ONLY if it contains <|prompt|> in the beginning of the comment.
        Tests positive trigger, missing trigger, and embedded trigger cases independently.
        """
        captured_dispatches = []

        class MockEngine:
            def process_webhook_prompt(self, comment_text, jira_issue_key, issue_summary="", project_key_hint="", preparations=None):
                captured_dispatches.append({
                    "jira_issue_key": jira_issue_key,
                    "comment_text": comment_text,
                    "preparations": preparations
                })
                return {"success": True, "task_id": f"task_{jira_issue_key}"}

        watcher = WebhookWatcher(pipeline_engine=MockEngine(), require_secret=False)

        # 1. Positive case: begins with <|prompt|>
        c1 = md_cases["MD-CASE-001"]
        t0 = time.perf_counter()
        p1 = watcher.receive_webhook({
            "webhookEvent": "comment_created",
            "comment": {"id": "1", "body": c1["comment"]},
            "issue": {"key": c1["jira_issue_key"], "fields": {"project": {"key": "PAY"}}}
        })
        res1 = watcher.dispatch_to_pipeline(p1)
        dur1 = (time.perf_counter() - t0) * 1000

        assert p1.is_ai_trigger is True
        assert p1.prompt_tag == "prompt"
        assert res1["success"] is True
        assert len(captured_dispatches) == 1
        assert captured_dispatches[-1]["jira_issue_key"] == "PAY-201"

        md_logger.log_test_case(
            case_id=c1["id"],
            category="normal",
            description=c1["description"],
            raw_comment=c1["comment"],
            detected_tag=p1.prompt_tag,
            stripped_comment=p1.in_memory_comment,
            passed=True,
            duration_ms=dur1,
            test_type="WEBHOOK PIPELINE TRIGGER GATING (<|prompt|> PREFIX)"
        )

        # 2. Negative case: regular comment without <|prompt|>
        c3 = md_cases["MD-CASE-003"]
        t0 = time.perf_counter()
        p3 = watcher.receive_webhook({
            "webhookEvent": "comment_created",
            "comment": {"id": "3", "body": c3["comment"]},
            "issue": {"key": c3["jira_issue_key"], "fields": {"project": {"key": "BUG"}}}
        })
        res3 = watcher.dispatch_to_pipeline(p3)
        dur3 = (time.perf_counter() - t0) * 1000

        assert p3.is_ai_trigger is False
        assert p3.prompt_tag is None
        assert res3["success"] is False
        assert "Ignored" in res3["reason"]
        # Ensure it was NOT dispatched downstream
        assert len(captured_dispatches) == 1

        md_logger.log_test_case(
            case_id=c3["id"],
            category="normal",
            description=c3["description"],
            raw_comment=c3["comment"],
            detected_tag=p3.prompt_tag,
            stripped_comment=p3.in_memory_comment,
            passed=True,
            duration_ms=dur3,
            test_type="WEBHOOK PIPELINE TRIGGER GATING (NO PROMPT TAG)"
        )

        # 3. Negative case: <|prompt|> embedded in middle (not at beginning)
        c4 = md_cases["MD-CASE-004"]
        t0 = time.perf_counter()
        p4 = watcher.receive_webhook({
            "webhookEvent": "comment_created",
            "comment": {"id": "4", "body": c4["comment"]},
            "issue": {"key": c4["jira_issue_key"], "fields": {"project": {"key": "DOCS"}}}
        })
        res4 = watcher.dispatch_to_pipeline(p4)
        dur4 = (time.perf_counter() - t0) * 1000

        assert p4.is_ai_trigger is False
        assert p4.prompt_tag is None
        assert res4["success"] is False
        assert len(captured_dispatches) == 1

        md_logger.log_test_case(
            case_id=c4["id"],
            category="edge_under",
            description=c4["description"],
            raw_comment=c4["comment"],
            detected_tag=p4.prompt_tag,
            stripped_comment=p4.in_memory_comment,
            passed=True,
            duration_ms=dur4,
            test_type="WEBHOOK PIPELINE TRIGGER GATING (EMBEDDED TAG REJECTION)"
        )

    def test_prompt_and_preparations_written_to_md_file_with_tag(self, md_cases, md_logger, tmp_path):
        """
        Requirement 2: When the prompt pushes through, the prompt and the preparations
        prompt is written to an md file, with a clear tag for where the preparation prompt starts.
        """
        writer = MDFileWriter(base_output_dir=tmp_path)
        task_id = "test_task_prep_tag"
        prompt_body = "Optimize database queries for user reports."
        prep_body = "Run EXPLAIN ANALYZE on slow query log and ensure pg_stat_statements is enabled."

        t0 = time.perf_counter()
        meta = writer.write_prompt_and_preparations(
            task_id=task_id,
            prompt_text=prompt_body,
            preparations=prep_body
        )
        dur = (time.perf_counter() - t0) * 1000

        prompt_file = Path(meta["prompt_file_path"])
        prep_file = Path(meta["preparations_file_path"])

        # Check files exist
        assert prompt_file.exists(), f"Expected prompt.md at {prompt_file}"
        assert prep_file.exists(), f"Expected preparations.md at {prep_file}"

        # Read prompt.md content
        content = prompt_file.read_text(encoding="utf-8")

        # Verify prompt.md contains ONLY the prompt
        assert content.strip() == prompt_body.strip()
        assert "<|preparations|>" not in content, "prompt.md must NOT contain the <|preparations|> tag"
        assert prep_body not in content, "prompt.md must NOT contain preparations instructions"

        # Verify preparations.md contains ONLY raw preparation instructions
        assert prep_file.read_text(encoding="utf-8").strip() == prep_body.strip()

        md_logger.log_test_case(
            case_id="MD-CASE-005",
            category="normal",
            description="Verify prompt and preparations are written to md file with clear start tag",
            raw_comment=f"<|prompt|> {prompt_body}\n<|preparations|> {prep_body}",
            detected_tag="prompt",
            stripped_comment=prompt_body,
            passed=True,
            duration_ms=dur,
            test_type="MD FILE WRITER - TAGGED PREPARATIONS FORMATTING",
            preparations=prep_body
        )

    def test_prompt_md_file_default_save_location(self, md_logger):
        """
        Requirement 3 (Part 1): Prompt md files should save by default to a folder
        within the project file path.
        """
        t0 = time.perf_counter()
        
        # Clear PROMPT_OUTPUT_DIR env if set to test default behavior
        old_val = os.environ.pop("PROMPT_OUTPUT_DIR", None)
        try:
            default_dir = get_prompt_output_dir()
            expected_default = ROOT_DIR / "staging"
            assert default_dir.resolve() == expected_default.resolve()

            # Ensure default folder is strictly inside project root
            assert ROOT_DIR in default_dir.resolve().parents or default_dir.resolve() == ROOT_DIR

            # Write a prompt file using PromptExtractor
            extractor = PromptExtractor()
            task_id = "test_default_save_location"
            ok, meta = extractor.extract_prompt("<|prompt|> Test default staging directory.", task_id)

            assert ok is True
            prompt_file = Path(meta["prompt_file_path"])
            assert prompt_file.exists()
            assert expected_default in prompt_file.parents
            assert prompt_file.name == "prompt.md"

            dur = (time.perf_counter() - t0) * 1000
            md_logger.log_test_case(
                case_id="MD-SAVE-DEFAULT",
                category="normal",
                description="Prompt md file saves by default to staging folder inside project root",
                raw_comment="<|prompt|> Test default staging directory.",
                detected_tag="prompt",
                stripped_comment="Test default staging directory.",
                passed=True,
                duration_ms=dur,
                test_type="MD SAVE LOCATION - DEFAULT PROJECT STAGING FOLDER"
            )
        finally:
            if old_val:
                os.environ["PROMPT_OUTPUT_DIR"] = old_val

    def test_prompt_md_file_custom_save_location_via_env(self, md_logger, tmp_path):
        """
        Requirement 3 (Part 2): Prompt md files should be able to be modified by the user
        by placing a new path in a .env file (PROMPT_OUTPUT_DIR).
        """
        t0 = time.perf_counter()
        custom_save_dir = tmp_path / "custom_user_prompts"
        os.environ["PROMPT_OUTPUT_DIR"] = str(custom_save_dir)

        try:
            resolved_dir = get_prompt_output_dir()
            assert resolved_dir.resolve() == custom_save_dir.resolve()

            extractor = PromptExtractor()
            task_id = "test_custom_env_task"
            comment = (
                "<|prompt|> Generate user reports API.\n"
                "<|preparations|> Seed test database with mock reports."
            )
            ok, meta = extractor.extract_prompt(comment, task_id)
            dur = (time.perf_counter() - t0) * 1000

            assert ok is True
            prompt_file = Path(meta["prompt_file_path"])
            prep_file = Path(meta["preparations_file_path"])

            # Verify both files saved in the user-specified directory
            assert prompt_file.exists()
            assert prep_file.exists()
            assert custom_save_dir in prompt_file.parents
            assert custom_save_dir in prep_file.parents

            # Verify prompt content contains only the prompt and preparations file contains preparations
            prompt_content = prompt_file.read_text(encoding="utf-8")
            assert prompt_content.strip() == "Generate user reports API."
            assert "<|preparations|>" not in prompt_content
            assert prep_file.read_text(encoding="utf-8").strip() == "Seed test database with mock reports."

            md_logger.log_test_case(
                case_id="MD-SAVE-CUSTOM-ENV",
                category="normal",
                description="Prompt md file saves to user-specified path configured via .env",
                raw_comment=comment,
                detected_tag="prompt",
                stripped_comment="Generate user reports API.",
                passed=True,
                duration_ms=dur,
                test_type="MD SAVE LOCATION - CUSTOM PATH VIA .ENV",
                preparations="Seed test database with mock reports."
            )
        finally:
            os.environ.pop("PROMPT_OUTPUT_DIR", None)

    def test_manual_jira_push_route_positive(self, client, md_logger):
        """
        Requirement 4: Create a route where the user can test this themselves manually
        with a push from their linked Jira site (POST /api/webhooks/test-jira-push).
        Positive test: valid prompt tag pushes through and returns diagnostic confirmation.
        """
        t0 = time.perf_counter()
        payload = {
            "webhookEvent": "comment_created",
            "comment": {
                "id": "man_1001",
                "body": (
                    "<|prompt|> Manual Jira test verification push.\n"
                    "<|preparations|> Verify live container integration."
                )
            },
            "issue": {
                "key": "MANUAL-101",
                "fields": {
                    "summary": "Manual Push Test",
                    "project": {"key": "MANUAL"}
                }
            }
        }

        response = client.post("/api/webhooks/test-jira-push", json=payload)
        dur = (time.perf_counter() - t0) * 1000

        assert response.status_code == 200
        data = response.json()

        assert data["test_status"] == "success"
        assert data["pushed_through_pipeline"] is True
        assert data["jira_issue_key"] == "MANUAL-101"
        assert data["prompt_tag"] == "prompt"
        assert data["has_preparations"] is True
        assert data["preparations"] == "Verify live container integration."
        assert "prompt_save_base_directory" in data

        md_logger.log_test_case(
            case_id="MD-ROUTE-POSITIVE",
            category="reception",
            description="Manual test route (/api/webhooks/test-jira-push) positive push with prompt and preparations",
            raw_comment=payload["comment"]["body"],
            detected_tag="prompt",
            stripped_comment=data["prompt_instructions"],
            passed=True,
            duration_ms=dur,
            test_type="MANUAL JIRA PUSH TEST ROUTE (POSITIVE DISPATCH)",
            preparations="Verify live container integration."
        )

    def test_manual_jira_push_route_ignored_without_tag(self, client, md_logger):
        """
        Requirement 4 (continued): Manual Jira push route correctly ignores comments
        without <|prompt|>.
        """
        t0 = time.perf_counter()
        payload = {
            "webhookEvent": "comment_created",
            "comment": {
                "id": "man_1002",
                "body": "Normal status update without AI prompt prefix."
            },
            "issue": {
                "key": "MANUAL-102",
                "fields": {
                    "summary": "Manual Push Test Ignored",
                    "project": {"key": "MANUAL"}
                }
            }
        }

        response = client.post("/api/webhooks/test-jira-push", json=payload)
        dur = (time.perf_counter() - t0) * 1000

        assert response.status_code == 200
        data = response.json()

        assert data["test_status"] == "ignored"
        assert data["pushed_through_pipeline"] is False
        assert "does not begin with" in data["reason"]

        md_logger.log_test_case(
            case_id="MD-ROUTE-IGNORED",
            category="reception",
            description="Manual test route (/api/webhooks/test-jira-push) ignores comment without prompt tag",
            raw_comment=payload["comment"]["body"],
            detected_tag=None,
            stripped_comment=payload["comment"]["body"],
            passed=True,
            duration_ms=dur,
            test_type="MANUAL JIRA PUSH TEST ROUTE (IGNORED UNTAGGED COMMENT)"
        )

    def test_md_file_writer_log_output_naming(self, md_logger):
        """
        Requirement: Make sure that anything saved indicates it is for the md file writer
        test in the file name (tests/test_logs/md_file_writer_*.log and *.json).
        """
        log_file = md_logger.log_file
        report_file = md_logger.report_file

        assert log_file is not None
        assert report_file is not None

        # Verify destination folder is tests/test_logs
        expected_log_dir = ROOT_DIR / "tests" / "test_logs"
        assert log_file.parent.resolve() == expected_log_dir.resolve()
        assert report_file.parent.resolve() == expected_log_dir.resolve()

        # Verify filename indicates it is for md file writer test
        assert log_file.name.startswith("md_file_writer_"), (
            f"Log file name {log_file.name} must start with md_file_writer_"
        )
        assert report_file.name.startswith("md_file_writer_"), (
            f"Report file name {report_file.name} must start with md_file_writer_"
        )

        assert log_file.exists()

    def test_files_staging_does_not_ingest_preparations_as_files(self, md_logger, tmp_path):
        """
        Verification: Ensure that when a comment has <|files|> followed by <|preparations|>,
        the preparations text is NEVER ingested as fake files in staging/files/, and prompt.md
        only contains the genuine files under <|files|>.
        """
        from backend.preprocessor.md_file_writer import MDFileWriter
        from backend.preprocessor.file_gatherer import FileGatherer
        from backend.watcher.webhook_watcher import WebhookPayloadFormatter

        comment = (
            "<|prompt|>\n"
            "Process report data and run analytics.\n\n"
            "<|files|>\n"
            "'/Users/dbearsong/Documents/User Profile - Dereck.txt'\n"
            "'/Users/dbearsong/Documents/User Profile - Dereck.docx'\n"
            "/Users/dbearsong/Documents/projects/python/job_scraper_and_analyzer/cron_debug.log\n\n"
            "<|preparations|>\n"
            "Get today's date and create a text file named update_log.txt.\n"
        )

        formatted = WebhookPayloadFormatter.format_payload({
            "webhookEvent": "comment_created",
            "comment": {"id": "sep_test", "body": comment},
            "issue": {"key": "PREP-FILE-001", "fields": {"summary": "Files and Prep Isolation Test"}}
        })

        assert len(formatted.files) == 3
        assert formatted.preparations == "Get today's date and create a text file named update_log.txt."

        writer = MDFileWriter(base_output_dir=tmp_path)
        gatherer = FileGatherer()

        t0 = time.perf_counter()
        w_res = writer.write_prompt_and_preparations(
            task_id="task_sep_test",
            prompt_text=formatted.in_memory_comment,
            preparations=formatted.preparations
        )

        s_res = gatherer.extract_and_stage_files(
            prompt_file_path=w_res["prompt_file_path"],
            task_staging_dir=w_res["task_staging_dir"],
            preparations=formatted.preparations
        )
        dur = (time.perf_counter() - t0) * 1000

        # Verify staged files manifest contains ONLY the 3 genuine files
        staged_manifest = s_res.get("staged_files", [])
        assert len(staged_manifest) == 3, f"Expected exactly 3 staged files, got {len(staged_manifest)}"
        manifest_names = [Path(sf["original_path"]).name for sf in staged_manifest]
        assert "User Profile - Dereck.txt" in manifest_names
        assert "User Profile - Dereck.docx" in manifest_names
        assert "cron_debug.log" in manifest_names

        # Verify disk files in task staging / files/ directory
        files_dir = Path(w_res["task_staging_dir"]) / "files"
        disk_files = [f.name for f in files_dir.iterdir()]
        assert len(disk_files) == 3, f"Expected 3 files in files/ folder, got {disk_files}"
        for unexpected in ["Get", "today's", "date", "and", "create", "a", "text", "file", "named", "update_log.txt"]:
            if unexpected not in ["update_log.txt"]:  # unless mentioned in files
                assert unexpected not in disk_files, f"Preparations word '{unexpected}' was erroneously created as a file!"

        # Verify prompt.md content contains ONLY the prompt instructions
        prompt_text = Path(w_res["prompt_file_path"]).read_text(encoding="utf-8")
        assert prompt_text.strip() == formatted.prompt_instructions.strip()
        assert "<|preparations|>" not in prompt_text
        assert "<|files|>" not in prompt_text
        assert "Get today's date" not in prompt_text
        assert "/workspace/staged_files" not in prompt_text

        md_logger.log_test_case(
            case_id="MD-PREP-FILE-ISOLATION",
            category="normal",
            description="Verified that preparations instructions are not ingested as fake files in staging",
            raw_comment=comment,
            detected_tag=formatted.prompt_tag,
            stripped_comment=formatted.in_memory_comment,
            passed=True,
            duration_ms=dur,
            test_type="FILES AND PREPARATIONS ISOLATION TEST",
            preparations=formatted.preparations
        )
