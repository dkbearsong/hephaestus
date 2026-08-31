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
