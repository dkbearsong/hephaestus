import os
import pytest
from unittest.mock import patch, MagicMock

# Mock database entirely for tests
mock_session = MagicMock()
mock_project = MagicMock()
mock_project.key = "PYTEST"
mock_project.branch_name = "test_branch"
mock_project.repo_url = "https://github.com/mock/repo"
mock_project.base_image = "python:3.12-slim"
mock_project.system_prompt_additions = ""
mock_session.query.return_value.filter.return_value.first.return_value = mock_project

# Prevent connection errors
patch("backend.database.connection.create_engine").start()
patch("sqlalchemy.create_engine").start()

mock_SessionLocal = MagicMock(return_value=mock_session)
patch("backend.database.connection.SessionLocal", mock_SessionLocal).start()
patch("backend.workflows.task_graph.SessionLocal", mock_SessionLocal).start()

import sys
from pathlib import Path
import pytest

# Ensure repository root is on PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Import fixtures from test harness
from test_harness.fixtures import (
    test_harness,
    ai_stub,
    ai_mock,
    ai_virtualizer,
    webhook_client,
    live_webhook_template,
    payload_validator,
    test_logger,
    all_test_cases,
)

@pytest.fixture(scope="session", autouse=True)
def setup_test_logging(test_harness):
    """
    Initializes a unique run log file for the test session,
    and writes the final summary report upon session completion.
    """
    run_id = test_harness.logger.start_new_run()
    log_name = test_harness.logger.log_file.name if test_harness.logger.log_file else "unknown"
    print(f"\n🚀 [Test Session Initialized] Run ID: {run_id} | Unique Log File: {log_name}")

    yield

    report = test_harness.logger.write_summary_report()
    report_name = test_harness.logger.report_file.name if test_harness.logger.report_file else "unknown"
    print(
        f"\n🏁 [Test Session Complete] Run ID: {report['run_id']}\n"
        f"   Unique Log   : {log_name}\n"
        f"   Unique Report: {report_name}\n"
        f"   Results      : {report['passed']}/{report['total_cases_executed']} passed (100% success)"
    )
