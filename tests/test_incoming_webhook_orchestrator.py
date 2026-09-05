import pytest
from test_harness.workspace_orchestrator.webhook_tester import incoming_webhook_tester


def test_incoming_webhook_prompt_new_local_container():
    """
    Tests receiving an incoming signed Jira webhook for PROMPT_NEW
    and verifies full downstream pipeline execution through WorkspaceOrchestrator.
    """
    res = incoming_webhook_tester.receive_and_test_webhook(
        ticket_key="WH-NEW-101",
        mode="PROMPT_NEW",
        target_platform="LOCAL_CONTAINER",
        prompt="Build asynchronous task queue service with Redis.",
        preparations="Move controller.py to src/controllers/\nInstall redis>=5.0.0\n",
        verbose=False
    )
    assert res["success"] is True
    assert res["http_status"] == 200
    assert res["verifications"]["webhook_accepted_200"] is True
    assert res["verifications"]["pipeline_dispatched"] is True
    assert res["verifications"]["workspace_created"] is True
    assert res["verifications"]["git_branch_valid"] is True
    assert res["verifications"]["provider_rules_enforced"] is True
    assert res["verifications"]["handoff_state_recorded"] is True
    assert res["verifications"]["staged_files_handled"] is True


def test_incoming_webhook_prompt_existing_google_jules():
    """
    Tests receiving an incoming signed Jira webhook for PROMPT mode
    targeting GOOGLE_JULES platform.
    """
    res = incoming_webhook_tester.receive_and_test_webhook(
        ticket_key="WH-EXIST-202",
        mode="PROMPT",
        target_platform="GOOGLE_JULES",
        prompt="Update payment processing retry backoff logic.",
        preparations="Verify zero uncommitted files rule for Jules.\n",
        verbose=False
    )
    assert res["success"] is True
    assert res["http_status"] == 200
    assert res["verifications"]["workspace_created"] is True
    assert res["verifications"]["git_branch_valid"] is True
    assert res["verifications"]["provider_rules_enforced"] is True
    assert res["verifications"]["handoff_state_recorded"] is True


def test_incoming_webhook_codex_cloud():
    """
    Tests receiving an incoming signed Jira webhook targeting CODEX_CLOUD.
    """
    res = incoming_webhook_tester.receive_and_test_webhook(
        ticket_key="WH-CODEX-303",
        mode="PROMPT_NEW",
        target_platform="CODEX_CLOUD",
        prompt="Implement FastAPI GraphQL server schema.",
        preparations="Configure Codex Cloud task metadata entry points.\n",
        verbose=False
    )
    assert res["success"] is True
    assert res["http_status"] == 200
    assert res["verifications"]["provider_rules_enforced"] is True
    assert res["verifications"]["handoff_state_recorded"] is True


def test_incoming_webhook_tampered_signature_rejected():
    """
    Tests security rejection: a webhook with tampered HMAC-SHA256 signature
    must be immediately rejected with HTTP 401 and not trigger orchestration.
    """
    res = incoming_webhook_tester.receive_and_test_webhook(
        ticket_key="WH-HACK-401",
        mode="PROMPT_NEW",
        target_platform="LOCAL_CONTAINER",
        tamper_signature=True,
        verbose=False
    )
    assert res["success"] is True
    assert res["http_status"] == 401
    assert res["verifications"]["tamper_rejected_401"] is True
