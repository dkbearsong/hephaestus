import pytest
from test_harness.manager import test_harness_manager

@pytest.fixture(scope="session")
def test_harness():
    """Provides the central TestHarness coordinator for the test session."""
    yield test_harness_manager
    test_harness_manager.teardown()

@pytest.fixture
def ai_stub(test_harness):
    """Provides an AI stub harness and ensures cleanup after test."""
    stub = test_harness.plug_in_ai_stub()
    yield stub
    test_harness.unplug_ai()

@pytest.fixture
def ai_mock(test_harness):
    """Provides an AI mock harness with interaction tracking."""
    mock = test_harness.plug_in_ai_mock()
    yield mock
    test_harness.unplug_ai()

@pytest.fixture
def ai_virtualizer(test_harness):
    """Provides an AI service virtualizer with dynamic simulation."""
    virt = test_harness.plug_in_ai_virtualizer()
    yield virt
    test_harness.unplug_ai()

@pytest.fixture
def webhook_client(test_harness):
    """Provides the webhook watcher test client."""
    test_harness.webhook_client.reset()
    return test_harness.webhook_client

@pytest.fixture
def live_webhook_template(test_harness):
    """Provides the live webhook template adapter."""
    return test_harness.live_template

@pytest.fixture
def payload_validator(test_harness):
    """Provides the payload schema and tag validator."""
    return test_harness.payload_validator

@pytest.fixture
def test_logger(test_harness):
    """Provides the test execution logger reporting to tests/test_logs/."""
    return test_harness.logger

@pytest.fixture(scope="session")
def all_test_cases(test_harness):
    """Loads all 50 test cases from test/test_data/cases.json."""
    return test_harness.data_loader.get_all_cases()
