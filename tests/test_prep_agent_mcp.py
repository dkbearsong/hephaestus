import os
import json
import pytest
import sys
import uuid
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional

# Ensure project root is in PYTHONPATH
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.config import (
    ServerConfig,
    UserPreferences,
    load_user_preferences,
    load_and_merge_servers,
    get_default_server_config
)
from services.builtin_tools_server import (
    resolve_safe_path,
    create_builtin_mcp_server
)
from services.mcp_manager import MCPManager, extract_tool_result_text
from services.prep_agent import PreparationAgent, convert_mcp_tool_to_schema
from services.models import PrepSummary


# ---------------------------------------------------------------------------
# 1. Configuration & User Preferences Tests
# ---------------------------------------------------------------------------

def test_server_config_validation():
    cfg = ServerConfig(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx"}
    )
    assert cfg.command == "npx"
    assert len(cfg.args) == 2
    assert cfg.env["GITHUB_PERSONAL_ACCESS_TOKEN"] == "ghp_xxx"
    assert cfg.cwd is None


def test_load_user_preferences_from_yaml(tmp_path):
    yaml_content = """
mcp_servers:
  github:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "ghp_12345"
  custom_linter:
    command: "python"
    args: ["-m", "my_custom_mcp_linter"]
"""
    pref_file = tmp_path / "user-preferences.yml"
    pref_file.write_text(yaml_content, encoding="utf-8")

    prefs = load_user_preferences(pref_file)
    assert "github" in prefs.mcp_servers
    assert "custom_linter" in prefs.mcp_servers
    assert prefs.mcp_servers["github"].command == "npx"
    assert prefs.mcp_servers["custom_linter"].args == ["-m", "my_custom_mcp_linter"]


def test_load_user_preferences_missing_file(tmp_path):
    missing_file = tmp_path / "does_not_exist.yml"
    prefs = load_user_preferences(missing_file)
    assert isinstance(prefs, UserPreferences)
    assert len(prefs.mcp_servers) == 0


def test_load_and_merge_servers(tmp_path):
    yaml_content = """
mcp_servers:
  custom_tool:
    command: "python"
    args: ["-c", "print('hello')"]
"""
    pref_file = tmp_path / "user-preferences.yml"
    pref_file.write_text(yaml_content, encoding="utf-8")

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    merged = load_and_merge_servers(pref_file, workspace)
    assert "builtin" in merged
    assert "custom_tool" in merged
    assert merged["builtin"].args[-1] == str(workspace.resolve())
    assert merged["custom_tool"].command == "python"


# ---------------------------------------------------------------------------
# 2. Built-in Tools Sandboxing & Path Traversal Guard Tests
# ---------------------------------------------------------------------------

def test_resolve_safe_path_valid(tmp_path):
    base = tmp_path / "sandbox"
    base.mkdir()
    file1 = base / "nested" / "app.py"
    file1.parent.mkdir()
    file1.touch()

    resolved = resolve_safe_path(base, "nested/app.py")
    assert resolved == file1.resolve()

    resolved_root = resolve_safe_path(base, ".")
    assert resolved_root == base.resolve()


def test_resolve_safe_path_traversal_blocked(tmp_path):
    base = tmp_path / "sandbox"
    base.mkdir()

    # Relative traversal attempt
    with pytest.raises(PermissionError) as exc_info:
        resolve_safe_path(base, "../secret.txt")
    assert "outside the allowed working directory" in str(exc_info.value)

    # Absolute traversal attempt
    with pytest.raises(PermissionError) as exc_info:
        resolve_safe_path(base, "/etc/passwd")
    assert "outside the allowed working directory" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 3. MCP Manager Lifecycle & Built-in Tools Execution
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_mcp_manager_builtin_tools_execution(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Create an initial inbox file to move
    inbox = workspace / ".harness_inbox"
    inbox.mkdir()
    (inbox / "config.sample.json").write_text('{"key": "val"}', encoding="utf-8")

    async with MCPManager.from_preferences(None, workspace) as mcp:
        tools = await mcp.get_available_tools()
        tool_names = [t.name for t in tools]
        assert "write_file" in tool_names
        assert "read_file" in tool_names
        assert "move_file" in tool_names
        assert "list_directory" in tool_names
        assert "run_command" in tool_names
        assert "complete_preparation" in tool_names

        # 1. Write file
        write_res = await mcp.call_tool("write_file", {"path": ".env", "content": "FOO=bar\n"})
        assert not getattr(write_res, "isError", False)
        assert (workspace / ".env").exists()
        assert (workspace / ".env").read_text() == "FOO=bar\n"

        # 2. Read file
        read_res = await mcp.call_tool("read_file", {"path": ".env"})
        assert not getattr(read_res, "isError", False)
        text = extract_tool_result_text(read_res)
        assert "FOO=bar" in text

        # 3. Move file from inbox to config/
        move_res = await mcp.call_tool("move_file", {
            "source": ".harness_inbox/config.sample.json",
            "destination": "config/config.json"
        })
        assert not getattr(move_res, "isError", False)
        assert (workspace / "config" / "config.json").exists()

        # 4. List directory
        list_res = await mcp.call_tool("list_directory", {"path": "."})
        assert not getattr(list_res, "isError", False)

        # 5. Run command
        cmd_res = await mcp.call_tool("run_command", {
            "command": f"{sys.executable} -c \"print('PYTHON_OK')\""
        })
        assert not getattr(cmd_res, "isError", False)
        cmd_text = extract_tool_result_text(cmd_res)
        assert "PYTHON_OK" in cmd_text

        # 6. Verify tracked file modifications
        assert ".env" in mcp.files_modified
        assert "config/config.json" in mcp.files_modified


@pytest.mark.anyio
async def test_mcp_manager_fault_tolerance(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # User preferences with a broken/non-existent command
    broken_yaml = """
mcp_servers:
  broken_server:
    command: "non_existent_binary_xyz_12345"
    args: ["--bad"]
"""
    pref_file = tmp_path / "user-preferences.yml"
    pref_file.write_text(broken_yaml, encoding="utf-8")

    # Starting MCPManager should NOT crash the entire pipeline
    async with MCPManager.from_preferences(pref_file, workspace) as mcp:
        tools = await mcp.get_available_tools()
        # Built-in tools should still be present and functional
        tool_names = [t.name for t in tools]
        assert "read_file" in tool_names
        assert "write_file" in tool_names


# ---------------------------------------------------------------------------
# 4. Tool Schema Conversion Tests
# ---------------------------------------------------------------------------

def test_convert_mcp_tool_to_schema():
    class DummyTool:
        name = "test_tool"
        description = "A test tool"
        inputSchema = {
            "type": "object",
            "properties": {"arg1": {"type": "string"}},
            "required": ["arg1"]
        }

    openai_schema = convert_mcp_tool_to_schema(DummyTool(), provider="openai")
    assert openai_schema["type"] == "function"
    assert openai_schema["function"]["name"] == "test_tool"
    assert "arg1" in openai_schema["function"]["parameters"]["properties"]

    anthropic_schema = convert_mcp_tool_to_schema(DummyTool(), provider="claude")
    assert anthropic_schema["name"] == "test_tool"
    assert "arg1" in anthropic_schema["input_schema"]["properties"]


# ---------------------------------------------------------------------------
# 5. PreparationAgent ReAct Tool-Calling Loop Tests
# ---------------------------------------------------------------------------

class MockLLMWithToolCalling:
    """Simulates LLM that emits a write_file tool call followed by complete_preparation."""
    def __init__(self):
        self.step = 0

    def call_chat(self, messages, tools, provider=None, temperature=0.1):
        self.step += 1
        class MockCall:
            def __init__(self, name, args):
                self.id = f"call_{name}_{os.urandom(2).hex()}"
                self.name = name
                self.args = args

        class MockResponse:
            def __init__(self, content, tool_calls):
                self.content = content
                self.tool_calls = tool_calls

        if self.step == 1:
            return MockResponse(
                content="I will write the environment file.",
                tool_calls=[MockCall("write_file", {"path": ".env", "content": "APP_ENV=testing\n"})]
            )
        else:
            return MockResponse(
                content="Preparations are complete.",
                tool_calls=[MockCall("complete_preparation", {
                    "status": "READY",
                    "detected_commands": {"test": "pytest", "build": None, "lint": None},
                    "files_modified": [".env"],
                    "blocker_reason": None
                })]
            )


@pytest.mark.anyio
async def test_prep_agent_arun_react_tool_calling(tmp_path):
    workspace = tmp_path / "agent_ws"
    workspace.mkdir()
    (workspace / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")

    mock_llm = MockLLMWithToolCalling()
    agent = PreparationAgent(llm_client=mock_llm)

    summary = await agent.arun(
        working_dir=workspace,
        branch_name="jira-TEST-123",
        merged_instructions="Configure test environment and verify pytest"
    )

    assert summary.status == "READY"
    assert summary.branch_name == "jira-TEST-123"
    assert summary.detected_commands["test"] == "pytest"
    assert ".env" in summary.files_modified
    assert (workspace / ".env").exists()
    assert (workspace / ".env").read_text() == "APP_ENV=testing\n"

    # Verify prep_summary.json persistence
    summary_file = workspace / "prep_summary.json"
    assert summary_file.exists()
    saved_data = json.loads(summary_file.read_text(encoding="utf-8"))
    assert saved_data["status"] == "READY"
    assert saved_data["branch_name"] == "jira-TEST-123"


class MockLLMWithJSONEmission:
    """Simulates LLM that emits structured JSON payload directly."""
    def call_chat(self, messages, tools, provider=None, temperature=0.1):
        class MockResponse:
            content = json.dumps({
                "status": "READY",
                "detected_commands": {"test": "npm test", "build": "npm run build"},
                "files_modified": ["package.json"],
                "blocker_reason": None
            })
            tool_calls = []

        return MockResponse()


@pytest.mark.anyio
async def test_prep_agent_arun_json_emission(tmp_path):
    workspace = tmp_path / "json_ws"
    workspace.mkdir()

    mock_llm = MockLLMWithJSONEmission()
    agent = PreparationAgent(llm_client=mock_llm)

    summary = await agent.arun(
        working_dir=workspace,
        branch_name="jira-NODE-456",
        merged_instructions="Inspect Node.js workspace"
    )

    assert summary.status == "READY"
    assert summary.detected_commands["test"] == "npm test"
    assert "package.json" in summary.files_modified

    # Verify prep_summary.json
    assert (workspace / "prep_summary.json").exists()


@pytest.mark.anyio
async def test_prep_agent_blocked_status(tmp_path):
    workspace = tmp_path / "blocked_ws"
    workspace.mkdir()

    agent = PreparationAgent(llm_client=None)

    summary = await agent.arun(
        working_dir=workspace,
        branch_name="jira-BLOCK-789",
        merged_instructions="BLOCK_TASK: missing AWS credentials for deployment"
    )

    assert summary.status == "BLOCKED"
    assert summary.blocker_reason is not None
    assert "unresolved blocker" in summary.blocker_reason

    # Verify prep_summary.json persisted even on BLOCKED
    summary_file = workspace / "prep_summary.json"
    assert summary_file.exists()
    data = json.loads(summary_file.read_text())
    assert data["status"] == "BLOCKED"


def test_prep_agent_sync_run_wrapper(tmp_path):
    workspace = tmp_path / "sync_ws"
    workspace.mkdir()

    inbox = workspace / ".harness_inbox"
    inbox.mkdir()
    (inbox / "helper.py").write_text("# helper\n", encoding="utf-8")

    agent = PreparationAgent(llm_client=None)
    summary = agent.run(
        working_dir=workspace,
        branch_name="jira-SYNC-111",
        merged_instructions="Move helper.py to src/\n"
    )

    assert summary.status == "READY"
    assert (workspace / "src" / "helper.py").exists()
    assert (workspace / "prep_summary.json").exists()


# ---------------------------------------------------------------------------
# 6. Jira Webhook to AI Agent Pipeline Execution Tests
# ---------------------------------------------------------------------------

def run_webhook_to_agent_test(
    ticket_key: Optional[str] = None,
    mode: str = "PROMPT_NEW",
    target_platform: str = "LOCAL_CONTAINER",
    prompt: Optional[str] = None,
    preparations: Optional[str] = None,
    webhook_url: Optional[str] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Receives an issue from a signed Jira webhook without requiring any ticket to be specified.
    Executes through the pipeline into the PreparationAgent (MCP AI agent), letting it run
    the required test in the workspace.
    """
    from test_harness.workspace_orchestrator.webhook_tester import incoming_webhook_tester

    # Auto-generate unique ticket key if not provided (zero ticket configuration required)
    ticket = ticket_key or f"AUTO-{uuid.uuid4().hex[:6].upper()}"

    test_prompt = prompt or "Build resilient task execution queue service."
    test_preparations = preparations or (
        "Verify workspace test suite by running pytest.\n"
        "Ensure pytest command is detected and verified.\n"
    )

    staged_files = {
        "controller.py": "# Controller Component\ndef handle_req(): return 'ok'\n",
        "test_controller.py": "def test_ok(): assert True\n",
        "run_service.sh": "#!/bin/bash\necho 'Service started'\n"
    }

    res = incoming_webhook_tester.receive_and_test_webhook(
        ticket_key=ticket,
        mode=mode,
        target_platform=target_platform,
        prompt=test_prompt,
        preparations=test_preparations,
        staged_files=staged_files,
        webhook_url=webhook_url,
        verbose=verbose
    )

    # Check that prep_summary.json exists and records test command
    ws_dir = res.get("working_directory")
    if ws_dir:
        summary_path = Path(ws_dir) / "prep_summary.json"
        if summary_path.exists():
            data = json.loads(summary_path.read_text(encoding="utf-8"))
            res["prep_summary"] = data
            res["verifications"]["prep_summary_exists"] = True
            res["verifications"]["prep_status_ready"] = (data.get("status") == "READY")
            res["verifications"]["test_command_detected"] = (
                data.get("detected_commands", {}).get("test") == "pytest"
            )

    return res


def test_receive_jira_webhook_and_run_agent_tests():
    """
    Tests receiving an issue from Jira webhooks with NO ticket specified on launch.
    Verifies that the webhook triggers the PreparationAgent, which uses MCP tools
    to execute the required pytest test on the workspace.
    """
    res = run_webhook_to_agent_test(
        ticket_key=None,  # No ticket specified!
        verbose=False
    )
    assert res["success"] is True
    assert res["http_status"] == 200
    assert res["verifications"]["webhook_accepted_200"] is True
    assert res["verifications"]["pipeline_dispatched"] is True
    assert res["verifications"]["workspace_created"] is True
    assert res["verifications"].get("prep_summary_exists") is True
    assert res["verifications"].get("prep_status_ready") is True
    assert res["verifications"].get("test_command_detected") is True


@pytest.mark.anyio
async def test_lm_studio_date_and_file_writer_agent():
    """
    Tests the PreparationAgent running with LM Studio / local LLM:
    1. Connects to datetime_tool and file_writer_tool via MCPManager.
    2. Pulls current date & time and writes a timestamped .txt into outputs/.
    3. Verifies file creation and content.
    """
    from test_lm_studio_mcp import run_lm_studio_mcp_test
    result = await run_lm_studio_mcp_test(
        clean_outputs=False,
        verbose=False
    )
    assert result["success"] is True
    assert result["created_file"] is not None
    assert Path(result["created_file"]).exists()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="PreparationAgent MCP & Jira Webhook Test Runner - Receives Jira webhooks without specifying a ticket and runs through to the AI agent."
    )
    parser.add_argument(
        "--webhook",
        action="store_true",
        default=True,
        help="Receive and test Jira webhook issue through to the AI agent (default: True, no ticket needed)"
    )
    parser.add_argument(
        "--listen",
        action="store_true",
        help="Start a live HTTP webhook listener daemon waiting for incoming Jira webhooks"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on when --listen is used (default: 8000)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host interface when --listen is used (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--ticket",
        type=str,
        default=None,
        help="Optional Jira issue key override (default: None, auto-generated so no ticket is needed)"
    )
    parser.add_argument(
        "--platform",
        choices=["LOCAL_CONTAINER", "GOOGLE_JULES", "CODEX_CLOUD"],
        default="LOCAL_CONTAINER",
        help="Downstream target platform (default: LOCAL_CONTAINER)"
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Optional prompt instructions override"
    )
    parser.add_argument(
        "--preparations",
        type=str,
        default=None,
        help="Optional preparations instructions override"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all unit and integration tests in the file via pytest"
    )

    args = parser.parse_args()

    if args.all:
        import subprocess
        sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))

    if args.listen:
        from listen_webhooks import print_banner
        import uvicorn
        print_banner(args.host, args.port)
        uvicorn.run("backend.main:app", host=args.host, port=args.port, reload=False, log_level="info")
        sys.exit(0)

    print("\n" + "=" * 80)
    print(" 🚀 RUNNING JIRA WEBHOOK TEST THROUGH TO AI AGENT (ZERO TICKET SPECIFIED)")
    print("=" * 80)
    res = run_webhook_to_agent_test(
        ticket_key=args.ticket,
        target_platform=args.platform,
        prompt=args.prompt,
        preparations=args.preparations,
        verbose=True
    )
    if res.get("success"):
        print("\n🎉 SUCCESS: Jira webhook received, AI agent executed required tests, and prep_summary.json generated!")
        sys.exit(0)
    else:
        print("\n❌ FAILED: Webhook or AI agent test execution failed.")
        sys.exit(1)

