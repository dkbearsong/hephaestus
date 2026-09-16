import unittest
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.parser import QualifierParser
from services.agents.registry import AgentRegistry, AgentSpec
from services.sandbox.guardrail import SandboxGuardrail
from services.sandbox.docker_runner import LocalDockerRunner
from services.sandbox.lifecycle import SandboxLifecycleManager
from backend.watcher.webhook_watcher import WebhookPayloadFormatter


class TestLocalDockerRunnerDispatch(unittest.IsolatedAsyncioTestCase):

    def test_qualifier_parser_tag_present(self):
        comment = "<|prompt|> <|agent:antigravity|> Refactor memory allocation in payment gateway"
        res = QualifierParser.parse_qualifiers(comment)
        self.assertEqual(res["agent_override"], "antigravity")
        self.assertEqual(res["target_platform"], "LOCAL_CONTAINER")
        self.assertEqual(res["cleaned_comment"], "<|prompt|>  Refactor memory allocation in payment gateway")

    def test_qualifier_parser_tag_omitted(self):
        comment = "<|prompt|> Refactor memory allocation in payment gateway"
        res = QualifierParser.parse_qualifiers(comment)
        self.assertIsNone(res["agent_override"])
        self.assertIsNone(res["target_platform"])
        self.assertEqual(res["cleaned_comment"], comment)

    def test_webhook_payload_formatter_with_agent_tag(self):
        raw_payload = {
            "issue": {
                "key": "PAY-101",
                "fields": {
                    "summary": "Fix payment retry logic",
                    "project": {"key": "PAY"}
                }
            },
            "comment": {
                "body": "<|prompt|> <|agent:claude_code|> Fix payment issue",
                "author": {"displayName": "Dev User"}
            }
        }
        formatted = WebhookPayloadFormatter.format_payload(raw_payload)
        self.assertEqual(formatted.jira_issue_key, "PAY-101")
        self.assertEqual(formatted.agent_override, "claude_code")
        self.assertEqual(formatted.target_platform, "LOCAL_CONTAINER")
        self.assertTrue(formatted.is_ai_trigger)

    def test_agent_registry_defaults(self):
        reg = AgentRegistry()
        specs = reg.list_specs()
        self.assertIn("antigravity", specs)
        self.assertIn("claude_code", specs)
        self.assertIn("aider", specs)
        self.assertIn("custom", specs)

        spec = reg.get("antigravity")
        self.assertEqual(spec.name, "antigravity")
        cmd = spec.entrypoint_cmd(Path("/workspace"), "/workspace/prompt.md")
        self.assertIn("--non-interactive", cmd)

    def test_sandbox_guardrail_actions(self):
        guardrail = SandboxGuardrail()
        # Allowed in sandbox
        self.assertTrue(guardrail.is_allowed_action("file_edit", "/workspace/src/app.py", "/workspace"))
        self.assertTrue(guardrail.is_allowed_action("shell_exec", "npm install", "/workspace"))

        # Escalation required outside sandbox
        self.assertFalse(guardrail.is_allowed_action("host_access", "bind_port_8080", "/workspace"))
        self.assertFalse(guardrail.is_allowed_action("external_deploy", "prod_server", "/workspace"))

    async def test_sandbox_guardrail_approval_flow(self):
        guardrail = SandboxGuardrail()
        run_id = "11111111-2222-3333-4444-555555555555"

        with patch("services.sandbox.guardrail.async_session_factory", None):
            req_task = asyncio.create_task(
                guardrail.request_permission(
                    run_id=run_id,
                    action="host_access",
                    command="bind_port_8080",
                    reason="Needs port 8080"
                )
            )
            await asyncio.sleep(0.01)
            guardrail.resolve_permission(run_id, approved=True)
            res = await req_task
            self.assertTrue(res)

    async def test_local_docker_runner_simulated_execution(self):
        runner = LocalDockerRunner()
        runner.docker_client = None # Force simulated mode
        reg = AgentRegistry()
        spec = reg.get("antigravity")

        res = await runner.run_container(
            run_id="22222222-3333-4444-5555-666666666666",
            workspace_dir=Path("/tmp/test_workspace"),
            agent_spec=spec
        )
        self.assertEqual(res["exit_code"], 0)
        self.assertTrue(res["simulated"])

    @patch("services.sandbox.lifecycle.jira_service")
    async def test_lifecycle_manager_success_flow(self, mock_jira):
        mock_runner = MagicMock()
        mock_runner.run_container = asyncio.iscoroutinefunction(mock_runner.run_container) and mock_runner.run_container or (
            lambda **kwargs: asyncio.sleep(0.001, result={"exit_code": 0, "simulated": True})
        )

        lifecycle = SandboxLifecycleManager(docker_runner=mock_runner)

        with patch("services.sandbox.lifecycle.async_session_factory", None), \
             patch("services.sandbox.lifecycle.GitRunner.run_git") as mock_git, \
             patch("services.sandbox.lifecycle.GitRunner.remote_exists", return_value=False):

            mock_git_res = MagicMock()
            mock_git_res.stdout = ""
            mock_git.return_value = mock_git_res

            res = await lifecycle.execute_run_lifecycle(
                run_id="33333333-4444-5555-6666-777777777777",
                ticket_key="PAY-101",
                workspace_dir=Path("/tmp/test_ws"),
                agent_name="antigravity"
            )

            self.assertTrue(res["success"])
            self.assertEqual(res["status"], "COMPLETED")
            self.assertEqual(res["branch_name"], "jira-pay-101-agent")


if __name__ == "__main__":
    unittest.main()
