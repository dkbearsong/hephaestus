import pytest
import json
from pathlib import Path
from backend.preprocessor.prompt_extractor import prompt_extractor
from backend.watcher.webhook_watcher import WebhookPayloadFormatter
from backend.coding_agents.google_jules import GoogleJulesOrchestrator
from backend.coding_agents.docker_sandbox_claude_codex import DockerSandboxClaudeCodexOrchestrator
from backend.coding_agents.openai_codex_cloud import OpenAICodexCloudOrchestrator
from backend.coding_agents.devin_ai import DevinAIOrchestrator
from test_harness.workspace_orchestrator.webhook_tester import incoming_webhook_tester


def test_extract_flags_yaml_block():
    """Verify <|flags|> YAML block is cleanly extracted and stripped."""
    comment = (
        "<|flags|>\n"
        "clone: false\n"
        "platform: GOOGLE_JULES\n"
        "max_retries: 3\n"
        "</|flags|>\n\n"
        "<|prompt|> Build payment retry queue."
    )
    is_prompt, meta = prompt_extractor.extract_prompt(comment, "task_flags_1")
    assert is_prompt is True
    assert meta["has_flags"] is True
    assert meta["flags"]["clone"] is False
    assert meta["flags"]["platform"] == "GOOGLE_JULES"
    assert meta["flags"]["max_retries"] == 3
    assert "<|flags|>" not in meta["prompt_instructions"]
    assert "Build payment retry queue." in meta["prompt_instructions"]


def test_webhook_watcher_extract_flags():
    """Verify WebhookPayloadFormatter extracts flags into FormattedWebhookPayload."""
    comment = (
        "<|flags|>\n"
        "clone: false\n"
        "target_agent: google_jules\n"
        "</|flags|>\n"
        "<|prompt|> Update webhook notification broker."
    )
    raw_payload = {
        "webhookEvent": "comment_created",
        "issue": {"key": "PAY-201", "fields": {"project": {"key": "PAY"}}},
        "comment": {"body": comment}
    }
    formatted = WebhookPayloadFormatter.format_payload(raw_payload)
    assert formatted.is_ai_trigger is True
    assert formatted.has_flags is True
    assert formatted.flags["clone"] is False
    assert formatted.flags["target_agent"] == "google_jules"
    assert "<|flags|>" not in formatted.prompt_instructions
    assert "Update webhook notification broker." in formatted.prompt_instructions


def test_agent_clone_requirements_attributes():
    """Verify cloud agents declare requires_local_clone = False while local agents declare True."""
    assert GoogleJulesOrchestrator.requires_local_clone is False
    assert OpenAICodexCloudOrchestrator.requires_local_clone is False
    assert DevinAIOrchestrator.requires_local_clone is False
    assert DockerSandboxClaudeCodexOrchestrator.requires_local_clone is True


def test_flags_clone_false_skips_git_clone_in_prompt_mode():
    """
    Verify that providing <|flags|>\nclone: false\n</|flags|> skips git clone
    even in PROMPT mode with a local container.
    """
    res = incoming_webhook_tester.receive_and_test_webhook(
        ticket_key="FLAGS-SKIP-CLONE-101",
        mode="PROMPT",
        target_platform="LOCAL_CONTAINER",
        prompt="Refactor database connection pool with flags.",
        flags={"clone": False},
        verbose=False
    )
    assert res["success"] is True
    working_dir = Path(res["working_directory"])
    assert working_dir.exists()

    # Check handoff file on disk
    handoff_path = working_dir / ".hephaestus_handoff.json"
    assert handoff_path.exists()
    handoff_data = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert handoff_data["ready_for_execution"] is True
    assert handoff_data["cloned"] is False
    assert handoff_data["flags"]["clone"] is False


def test_google_jules_skips_clone_by_default_without_flags():
    """
    Verify that Google Jules (cloud agent) automatically skips local git clone by default
    without needing an explicit <|flags|> tag.
    """
    res = incoming_webhook_tester.receive_and_test_webhook(
        ticket_key="JULES-AUTO-SKIP-101",
        mode="PROMPT",
        target_platform="GOOGLE_JULES",
        prompt="Implement async Jules event pipeline.",
        verbose=False
    )
    assert res["success"] is True
    working_dir = Path(res["working_directory"])
    assert working_dir.exists()

    handoff_path = working_dir / ".hephaestus_handoff.json"
    assert handoff_path.exists()
    handoff_data = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert handoff_data["ready_for_execution"] is True
    assert handoff_data["cloned"] is False
