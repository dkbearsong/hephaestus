import uuid
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from backend.db.service import async_session_factory
from backend.db.models import Run, RunEvent

logger = logging.getLogger("hephaestus.guardrail")

class PermissionPendingError(Exception):
    """Raised when an agent attempt requires human authorization and pauses execution."""
    def __init__(self, run_id: str, action: str, command: str, reason: str):
        self.run_id = run_id
        self.action = action
        self.command = command
        self.reason = reason
        super().__init__(f"Run {run_id} paused awaiting permission for action '{action}': {command}")


class SandboxGuardrail:
    """
    Enforces sandbox boundary rules.
    Autonomous inside /workspace, but intercepts breakout/escalation calls.
    """

    def __init__(self):
        self._pending_events: Dict[str, asyncio.Event] = {}
        self._approval_decisions: Dict[str, bool] = {}

    def is_allowed_action(self, action: str, target: str, workspace_dir: str) -> bool:
        """
        Determines if an action can be executed autonomously inside container sandbox.
        Inside workspace (file edits, local installs) -> True.
        Host access, external port bindings, external deploy, or out-of-workspace writes -> False.
        """
        lower_action = (action or "").lower()
        lower_target = (target or "").lower()

        # In-sandbox commands/tool calls are permitted
        if lower_action in ("file_edit", "shell_exec", "package_install", "local_build"):
            if lower_action == "file_edit" and target and workspace_dir:
                if not target.startswith(workspace_dir) and not target.startswith("/workspace"):
                    return False
            return True

        # Escalate external network / host access
        if lower_action in ("host_access", "port_bind", "external_deploy", "host_write"):
            return False

        if "deploy" in lower_target or "host" in lower_target or "port" in lower_target:
            return False

        return True

    async def request_permission(
        self,
        run_id: str,
        action: str,
        command: str,
        reason: str
    ) -> bool:
        """
        Pauses container/agent execution, updates runs.status = 'AWAITING_PERMISSION',
        persists run_event type 'PERMISSION_REQUESTED', and waits for human approval.
        """
        logger.warning(f"[Guardrail] Permission requested for run {run_id}: {action} - {command}")

        # Update DB run status and record event
        if async_session_factory:
            async with async_session_factory() as session:
                run_uuid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id
                run = await session.get(Run, run_uuid)
                if run:
                    run.status = "AWAITING_PERMISSION"
                    event = RunEvent(
                        run_id=run.id,
                        event_type="PERMISSION_REQUESTED",
                        level="WARNING",
                        payload={
                            "action": action,
                            "command": command,
                            "reason": reason
                        }
                    )
                    session.add(event)
                    await session.commit()

        # Set up waiting event for async approval
        event_key = str(run_id)
        evt = asyncio.Event()
        self._pending_events[event_key] = evt

        try:
            # Wait for approval signal
            await evt.wait()
            approved = self._approval_decisions.get(event_key, False)
            return approved
        finally:
            self._pending_events.pop(event_key, None)
            self._approval_decisions.pop(event_key, None)

    def resolve_permission(self, run_id: str, approved: bool):
        """
        Called when human approves or denies via API endpoint.
        Signals the waiting runner process to proceed or abort.
        """
        event_key = str(run_id)
        self._approval_decisions[event_key] = approved
        evt = self._pending_events.get(event_key)
        if evt:
            evt.set()


sandbox_guardrail = SandboxGuardrail()
