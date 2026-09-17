import os
import uuid
import logging
from backend.db.service import (
    create_run,
    update_run_status,
    append_event,
    create_run_sync,
    update_run_status_sync,
    append_event_sync
)
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from backend.config import preferences
from backend.database.connection import SessionLocal
from backend.database.models import Project, Ticket, WorkLog, ChatMessage, AgentNotification
from backend.jira_service.client import jira_service as default_jira_service
from backend.preprocessor.prompt_extractor import prompt_extractor as default_prompt_extractor
from backend.preprocessor.file_gatherer import file_gatherer as default_file_gatherer
from backend.preprocessor.preparations_graph import preparations_runner as default_preparations_runner
from backend.coding_agents.orchestrator import coding_agent_orchestrator as default_coding_orchestrator
from backend.harness import get_active_harness

logger = logging.getLogger("hephaestus.workflows")

class HephaestusWorkflowEngine:
    """
    Main workflow orchestrator with pluggable component architecture.
    Sequences incoming webhook -> prompt extraction -> LangGraph preparations ->
    Coding Agent Orchestrator (Google Jules, Grok Build, OpenAI Codex, Docker Sandbox, Devin, OpenHands) ->
    review logs and Jira notification.
    """

    def __init__(
        self,
        harness: Optional[Any] = None,
        jira_client: Optional[Any] = None,
        coding_orchestrator: Optional[Any] = None,
        prompt_ext: Optional[Any] = None,
        file_gath: Optional[Any] = None,
        prep_runner: Optional[Any] = None,
        db_session_factory: Optional[Any] = None,
    ):
        self._harness = harness
        self._jira_client = jira_client
        self._coding_orchestrator = coding_orchestrator
        self._prompt_ext = prompt_ext
        self._file_gath = file_gath
        self._prep_runner = prep_runner
        self._db_session_factory = db_session_factory

    @property
    def harness(self):
        return self._harness if self._harness is not None else get_active_harness()

    @property
    def coding_orchestrator(self):
        return self._coding_orchestrator if self._coding_orchestrator is not None else default_coding_orchestrator

    @property
    def jira_service(self):
        return self._jira_client if self._jira_client is not None else default_jira_service

    @property
    def prompt_extractor(self):
        return self._prompt_ext if self._prompt_ext is not None else default_prompt_extractor

    @property
    def file_gatherer(self):
        return self._file_gath if self._file_gath is not None else default_file_gatherer

    @property
    def preparations_runner(self):
        return self._prep_runner if self._prep_runner is not None else default_preparations_runner

    def get_session(self):
        factory = self._db_session_factory or SessionLocal
        return factory()

    def process_webhook_prompt(
        self,
        comment_text: str,
        jira_issue_key: str,
        issue_summary: str = "",
        project_key_hint: str = "",
        preparations: Optional[str] = None,
        target_agent: Optional[str] = None,
        is_new_project: Optional[bool] = None,
        flags: Optional[Dict[str, Any]] = None,
        parent_issue_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Main workflow pipeline triggered by incoming Jira Webhook.
        1. Check trigger prefix (<|prompt|> or <|prompt-new|>) and optional <|preparations|>
        2. Remove trigger label in Jira so further updates won't re-fire
        3. Extract prompt and save to .md (and preparations to preparations.md)
        4. Gather & stage files (<|files|>) and rewrite container paths
        4.5. Run LangGraph LLM Preparations step with MCP tools across preferred provider
        5. Pass task to Coding Agent Orchestrator which initiates containerized sandbox & executes prompt
        6. Pause if question/external access needed (triggers RED notification),
           otherwise save WorkLog & diff (triggers YELLOW notification).
        """
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        logger.info("Processing incoming webhook for issue %s (Task ID: %s)", jira_issue_key, task_id)

        # Step 1: Prompt extraction (includes optional <|additional values|>)
        is_prompt, prompt_meta = self.prompt_extractor.extract_prompt(comment_text, task_id, jira_issue_key=jira_issue_key)
        if not is_prompt:
            # Check if comment_text was already stripped of prompt prefix by the webhook watcher
            if comment_text and comment_text.strip():
                from backend.preprocessor.md_file_writer import md_file_writer
                files, prompt_instructions = self.prompt_extractor.extract_files(comment_text)
                writer_res = md_file_writer.write_prompt_and_preparations(
                    task_id=task_id,
                    prompt_text=prompt_instructions,
                    preparations=preparations
                )
                is_prompt = True
                prompt_meta = {
                    "task_id": task_id,
                    "is_new_project": bool(is_new_project),
                    "flags": flags or {},
                    "has_flags": bool(flags),
                    "raw_text": comment_text,
                    "cleaned_prompt": comment_text,
                    "prompt_instructions": prompt_instructions,
                    "files": files,
                    "task_staging_dir": writer_res["task_staging_dir"],
                    "prompt_file_path": writer_res["prompt_file_path"],
                    "preparations": preparations
                }
            else:
                logger.info("Comment does not contain trigger prefix. Skipping.")
                return {"success": False, "reason": "No prompt trigger prefix found"}

        # Determine mode, agent, and platform
        is_new_proj = is_new_project if is_new_project is not None else prompt_meta.get("is_new_project", False)
        run_mode = "PROMPT_NEW" if is_new_proj else "PROMPT"
        effective_agent = target_agent or getattr(preferences.harness, "active", "google_jules")

        platform_map = {
            "google_jules": "GOOGLE_JULES",
            "jules": "GOOGLE_JULES",
            "openai_codex_cloud": "CODEX_CLOUD",
            "codex_cloud": "CODEX_CLOUD",
            "codex": "CODEX_CLOUD",
            "docker_sandbox_claude_codex": "LOCAL_CONTAINER",
            "local_container": "LOCAL_CONTAINER",
            "grok_build": "LOCAL_CONTAINER",
            "grok": "LOCAL_CONTAINER",
            "devin_ai": "LOCAL_CONTAINER",
            "devin": "LOCAL_CONTAINER",
            "cursor_agent": "LOCAL_CONTAINER",
            "cursor_dev_container": "LOCAL_CONTAINER",
            "cursor_devcontainer": "LOCAL_CONTAINER",
            "antigravity": "LOCAL_CONTAINER",
            "claude_code": "LOCAL_CONTAINER",
            "aider": "LOCAL_CONTAINER",
            "custom": "LOCAL_CONTAINER"
        }
        resolved_platform = platform_map.get(
            str(effective_agent).lower() if effective_agent else "",
            "GOOGLE_JULES" if str(effective_agent).lower() in ("google_jules", "jules") else "LOCAL_CONTAINER"
        )
        initial_branch = f"hephaestus/{jira_issue_key.lower()}-{task_id}"

        run_id = create_run_sync(
            jira_key=jira_issue_key,
            mode=run_mode,
            target_platform=resolved_platform,
            status="QUEUED",
            branch_name=initial_branch,
            metrics={"agent_name": effective_agent, "task_id": task_id}
        )
        append_event_sync(
            run_id=run_id,
            event_type="TASK_INITIALIZED",
            payload={
                "jira_key": jira_issue_key,
                "task_id": task_id,
                "agent": effective_agent,
                "platform": resolved_platform,
                "mode": run_mode,
                "summary": issue_summary
            },
            level="INFO"
        )

        # Step 2: Remove trigger label in Jira to prevent infinite webhook loops
        self.jira_service.remove_trigger_label(jira_issue_key)

        # Step 3 & 4: Gather & stage files and process preparations instructions
        staging_dir = prompt_meta["task_staging_dir"]
        prompt_file = prompt_meta["prompt_file_path"]
        effective_prep = preparations or prompt_meta.get("preparations")
        stage_res = self.file_gatherer.extract_and_stage_files(
            prompt_file,
            staging_dir,
            preparations=effective_prep,
            files=prompt_meta.get("files", [])
        )
        staged_files = stage_res.get("staged_files", [])
        cleaned_prompt = stage_res.get("updated_prompt", prompt_meta["cleaned_prompt"])

        # Step 4.5: Preparations LLM Step (LangGraph + Multi-Provider + MCP Tools)
        prep_result: Optional[Dict[str, Any]] = None
        if effective_prep and getattr(preferences.preparations_step, "enabled", True):
            logger.info("[Workflow Pipeline] Executing Preparations LangGraph step for %s (Task: %s)", jira_issue_key, task_id)
            update_run_status_sync(run_id, status="PREPARING")
            append_event_sync(
                run_id=run_id,
                event_type="PREPARATIONS_STARTED",
                payload={
                    "preparations": effective_prep[:200],
                    "provider": getattr(preferences.preparations_step, "provider", "gemini")
                },
                level="INFO"
            )
            prep_result = self.preparations_runner.run_preparations(
                task_id=task_id,
                preparations_prompt=effective_prep,
                staging_dir=staging_dir,
                run_id=run_id
            )
            append_event_sync(
                run_id=run_id,
                event_type="PREPARATIONS_COMPLETED",
                payload={
                    "end_token_received": prep_result.get("end_token_received"),
                    "final_response": prep_result.get("final_response")
                },
                level="INFO"
            )
            logger.info("[Workflow Pipeline] Preparations step completed. End-of-Token received: %s. Continuing to Coding Agent stage.",
                        prep_result.get("end_token_received"))

        # Determine project key
        proj_key = project_key_hint or jira_issue_key.split("-")[0] if "-" in jira_issue_key else "DEFAULT"
        is_new_proj = is_new_project if is_new_project is not None else prompt_meta.get("is_new_project", False)

        session = self.get_session()
        try:
            # Find or create project
            project = session.query(Project).filter(Project.key == proj_key).first()
            if not project:
                project = Project(
                    name=f"Project {proj_key}",
                    key=proj_key,
                    jira_key=proj_key,
                    jira_ticket_key=jira_issue_key,
                    system_prompt_additions="Adhere to standard code style and provide clear verification notes."
                )
                session.add(project)
                session.commit()

            # Find or create ticket
            ticket = session.query(Ticket).filter(
                Ticket.project_id == project.id,
                Ticket.jira_key == jira_issue_key
            ).first()

            effective_issue_key = parent_issue_key if parent_issue_key else jira_issue_key
            branch_name = f"hephaestus/{effective_issue_key.lower()}-{task_id}"
            if not ticket:
                ticket = Ticket(
                    project_id=project.id,
                    jira_key=jira_issue_key,
                    title=issue_summary or f"Task for {jira_issue_key}",
                    branch_name=branch_name,
                    status="in_progress"
                )
                session.add(ticket)
                session.commit()
            else:
                ticket.status = "in_progress"
                if not ticket.branch_name:
                    ticket.branch_name = branch_name
                session.commit()

            # Bridge to WorkspaceOrchestrator (scaffolding, provider prep, prep agent, handoff)
            handoff_record = None
            try:
                from services.models import WorkspaceTriggerPayload
                from services.workspace_orchestrator import workspace_orchestrator
                from pathlib import Path
                from backend.config import ROOT_DIR

                workspaces_root = ROOT_DIR / "sandboxes" / "workspaces"
                workspaces_root.mkdir(parents=True, exist_ok=True)

                resolved_repo = getattr(project, "repo_url", None)
                if not resolved_repo and not is_new_proj:
                    resolved_repo = os.getenv("DEFAULT_REPO_URL") or (str(ROOT_DIR) if (ROOT_DIR / ".git").exists() else None)

                # Determine if cloning is required or skipped based on flags and agent type
                merged_flags = flags or prompt_meta.get("flags", {})
                agent_instance = self.coding_orchestrator.get_agent(effective_agent)
                agent_needs_clone = getattr(agent_instance, "requires_local_clone", True)

                flag_clone = merged_flags.get("clone")
                flag_skip_clone = merged_flags.get("skip_clone")
                if flag_clone is not None:
                    skip_clone = not bool(flag_clone)
                elif flag_skip_clone is not None:
                    skip_clone = bool(flag_skip_clone)
                else:
                    skip_clone = not agent_needs_clone

                ws_payload = WorkspaceTriggerPayload(
                    ticket_key=jira_issue_key,
                    mode="PROMPT_NEW" if is_new_proj else "PROMPT",
                    target_platform=resolved_platform,
                    repo_url=resolved_repo,
                    staging_dir=Path(staging_dir),
                    workspaces_root=workspaces_root,
                    custom_branch_name=ticket.branch_name,
                    skip_clone=skip_clone,
                    flags=merged_flags
                )
                handoff_state = workspace_orchestrator.orchestrate(ws_payload)
                ticket.branch_name = handoff_state.branch_name
                handoff_record = handoff_state.model_dump()
                if handoff_state.repo_url and not project.repo_url:
                    project.repo_url = handoff_state.repo_url
                    session.commit()

                update_run_status_sync(
                    run_id,
                    status="PREPARING",
                    branch_name=ticket.branch_name,
                    prep_summary=handoff_record.get("prep_summary")
                )
                append_event_sync(
                    run_id=run_id,
                    event_type="WORKSPACE_ORCHESTRATED",
                    payload={
                        "working_directory": handoff_record.get("working_directory"),
                        "branch_name": handoff_record.get("branch_name"),
                        "target_platform": handoff_record.get("target_platform"),
                        "ready_for_execution": handoff_record.get("ready_for_execution")
                    },
                    level="INFO"
                )
            except Exception as e:
                logger.warning(f"WorkspaceOrchestrator step encountered: {e}")

            # If workspace preparation was blocked, skip coding agent platform dispatch
            if handoff_record and not handoff_record.get("ready_for_execution", True):
                blocker_reason = handoff_record.get("prep_summary", {}).get("blocker_reason") or "Preparation phase blocked"
                logger.warning(
                    f"Skipping coding agent platform dispatch for {jira_issue_key}: {blocker_reason}"
                )
                update_run_status_sync(run_id, status="FAILED", error_message=blocker_reason)
                append_event_sync(
                    run_id=run_id,
                    event_type="RUN_FAILED",
                    payload={"reason": blocker_reason},
                    level="ERROR"
                )
                return {
                    "success": False,
                    "task_id": task_id,
                    "run_id": str(run_id) if run_id else None,
                    "jira_key": jira_issue_key,
                    "status": "BLOCKED",
                    "reason": blocker_reason,
                    "workspace_orchestration": handoff_record
                }

            # Step 5: Execute with Coding Agent Orchestrator
            # (which validates prompt, initiates container environment, and executes task)
            update_run_status_sync(run_id, status="CODING", branch_name=ticket.branch_name)
            append_event_sync(
                run_id=run_id,
                event_type="CODING_STARTED",
                payload={
                    "agent": effective_agent,
                    "platform": resolved_platform,
                    "branch": ticket.branch_name
                },
                level="INFO"
            )
            active_harness = self.harness
            effective_repo = project.repo_url or (handoff_record.get("repo_url") if handoff_record else None) or resolved_repo
            container_info = {
                "project_key": project.key,
                "branch_name": ticket.branch_name,
                "repo_url": effective_repo,
                "staged_files": staged_files,
                "is_new_project": is_new_proj,
                "preparations_result": prep_result,
                "workspace_orchestration": handoff_record
            }

            if hasattr(self, "_harness") and self._harness is not None:
                # Test stub/mock or specific harness override
                harness_result = self._harness.run_task(
                    prompt=cleaned_prompt,
                    container_info=container_info,
                    project_config={"name": project.name, "key": project.key, "branch_name": ticket.branch_name, "repo_url": effective_repo},
                    system_prompt_additions=project.system_prompt_additions
                )
            else:
                # Dispatch via CodingAgentOrchestrator
                harness_result = self.coding_orchestrator.execute_workflow(
                    prompt=cleaned_prompt,
                    project_key=project.key,
                    branch_name=ticket.branch_name,
                    repo_url=effective_repo,
                    staged_files=staged_files,
                    is_new_project=is_new_proj,
                    system_prompt_additions=project.system_prompt_additions,
                    preparations_result=prep_result,
                    target_agent=effective_agent
                )

            # Stream logs from coding agent into run_events
            if harness_result.full_log:
                for line in harness_result.full_log.splitlines():
                    line = line.strip()
                    if line:
                        append_event_sync(
                            run_id=run_id,
                            event_type="DOCKER_STDOUT",
                            payload={"log": line},
                            level="INFO"
                        )

            if harness_result.git_diff:
                append_event_sync(
                    run_id=run_id,
                    event_type="DIFF_GENERATED",
                    payload={
                        "summary_changes": harness_result.summary_changes,
                        "diff": harness_result.git_diff
                    },
                    level="INFO"
                )

            ticket.container_id = f"container_{project.key}_{ticket.branch_name}"
            ticket.image_id = f"sandbox_{effective_agent or 'active'}"
            session.commit()

            # Step 6: Handle Result (Paused vs Completed)
            now = datetime.now(timezone.utc)
            if harness_result.status == "paused_waiting_input":
                ticket.status = "paused_waiting_input"

                update_run_status_sync(
                    run_id,
                    status="AWAITING_PERMISSION",
                    error_message=harness_result.question_for_user
                )
                append_event_sync(
                    run_id=run_id,
                    event_type="PERMISSION_REQUESTED",
                    payload={
                        "question": harness_result.question_for_user,
                        "requested_permission": harness_result.requested_permission
                    },
                    level="WARNING"
                )

                # Create Agent Notification (RED SHAKING ICON)
                notif = AgentNotification(
                    ticket_id=ticket.id,
                    project_id=project.id,
                    type="needs_input",
                    title=f"User Action Required: {ticket.jira_key}",
                    message=harness_result.question_for_user or "Agent paused and requires approval or input to proceed.",
                    status="pending",
                    action_url=f"/tickets/{ticket.id}"
                )
                session.add(notif)

                # Record Chat Message from Agent
                msg = ChatMessage(
                    ticket_id=ticket.id,
                    project_id=project.id,
                    sender="agent",
                    message_type="question",
                    content=harness_result.question_for_user or "I have paused this task and require your input.",
                    metadata_json=harness_result.requested_permission or {},
                    status="pending"
                )
                session.add(msg)
                session.commit()

                return {
                    "success": True,
                    "status": "paused_waiting_input",
                    "task_id": task_id,
                    "run_id": str(run_id) if run_id else None,
                    "ticket_id": ticket.id,
                    "question": harness_result.question_for_user,
                    "preparations_result": prep_result
                }

            elif harness_result.status == "failed":
                # Agent refused dispatch or aborted before producing changes (e.g. missing
                # target branch in GitHub). Fail loudly instead of reporting review_ready.
                ticket.status = "failed"
                failure_reason = harness_result.what_was_wrong or harness_result.summary_changes or "Coding agent dispatch failed."

                update_run_status_sync(run_id, status="FAILED", error_message=failure_reason)
                append_event_sync(
                    run_id=run_id,
                    event_type="RUN_FAILED",
                    payload={"error": failure_reason},
                    level="ERROR"
                )

                session.add(AgentNotification(
                    ticket_id=ticket.id,
                    project_id=project.id,
                    type="failed",
                    title=f"Dispatch Failed: {ticket.jira_key}",
                    message=failure_reason,
                    status="pending",
                    action_url=f"/tickets/{ticket.id}"
                ))
                session.commit()

                self.jira_service.add_comment(
                    ticket.jira_key,
                    f"❌ **Coding Agent Dispatch Failed**: {failure_reason}\n\n"
                    f"No changes were produced. Please resolve the blocker and re-run the prompt."
                )

                return {
                    "success": False,
                    "status": "failed",
                    "task_id": task_id,
                    "run_id": str(run_id) if run_id else None,
                    "ticket_id": ticket.id,
                    "reason": failure_reason,
                    "workspace_orchestration": handoff_record
                }

            else: # completed
                ticket.status = "review_ready"

                # Check if a live cloud agent session was started or if changes need commit & PR
                pr_info = None
                working_dir_path = handoff_record.get("working_directory") if handoff_record else None
                has_remote_jules = bool(
                    harness_result.session_id or
                    (harness_result.full_log and "[Google Jules API] Connected to live Jules API" in harness_result.full_log)
                )

                if has_remote_jules:
                    logger.info("[Workflow Pipeline] Remote Google Jules session active (%s). AUTO_CREATE_PR will be handled by Jules in cloud.", harness_result.session_id)
                    self.jira_service.add_comment(
                        ticket.jira_key,
                        f"🚀 **Google Jules Task Dispatched**: Remote session `{harness_result.session_id or 'active'}` created in Google Cloud Workspace.\n\n"
                        f"Jules is processing the changes and will automatically open a Pull Request upon completion."
                    )
                else:
                    # In local sandbox / fallback mode, commit any generated code and create PR
                    if working_dir_path:
                        try:
                            from services.scaffolding import GitRunner
                            wdir = Path(working_dir_path)
                            GitRunner.run_git(["add", "."], cwd=wdir)
                            status_res = GitRunner.run_git(["status", "--porcelain"], cwd=wdir)
                            if status_res.stdout.strip():
                                GitRunner.run_git(
                                    ["commit", "-m", f"feat({ticket.jira_key.lower()}): automated implementation by {effective_agent}"],
                                    cwd=wdir
                                )
                            if GitRunner.remote_exists(wdir, "origin"):
                                GitRunner.push_branch(wdir, ticket.branch_name, remote="origin", set_upstream=True)
                        except Exception as git_err:
                            logger.warning(f"Git commit/push in completed stage encountered: {git_err}")

                    # Attempt GitHub PR creation
                    target_repo_for_pr = effective_repo or (handoff_record.get("repo_url") if handoff_record else None)
                    if target_repo_for_pr:
                        try:
                            from services.github_service import github_service
                            pr_info = github_service.create_pull_request(
                                repo=target_repo_for_pr,
                                head_branch=ticket.branch_name,
                                base_branch="main",
                                title=f"[{ticket.jira_key}] {ticket.title}",
                                body=f"Automated pull request submitted by Hephaestus ({effective_agent}).\n\n### Task Instructions\n{cleaned_prompt}\n\n### Changes Summary\n{harness_result.summary_changes or 'Automated implementation completed.'}"
                            )
                            logger.info(f"Created GitHub Pull Request: {pr_info.get('html_url')}")
                            self.jira_service.add_comment(
                                ticket.jira_key,
                                f"✅ **Implementation Completed**: Coding agent completed task.\n\n"
                                f"🔗 **Pull Request**: [{pr_info.get('title', 'View PR')}]({pr_info.get('html_url')})"
                            )
                        except Exception as pr_err:
                            logger.warning(f"Could not create GitHub PR: {pr_err}")

                # Persist Work Log with diff and breakdown
                work_log = WorkLog(
                    ticket_id=ticket.id,
                    project_id=project.id,
                    timestamp=now,
                    prompt_raw=comment_text,
                    prompt_processed=cleaned_prompt,
                    staged_files=staged_files,
                    status="completed",
                    summary_changes=harness_result.summary_changes,
                    what_was_wrong=harness_result.what_was_wrong,
                    what_was_done=harness_result.what_was_done,
                    user_check_items=harness_result.user_check_items,
                    git_diff=harness_result.git_diff,
                    full_log=harness_result.full_log
                )
                session.add(work_log)

                # Create Agent Notification (YELLOW COMPLETED ICON)
                notif = AgentNotification(
                    ticket_id=ticket.id,
                    project_id=project.id,
                    type="completed",
                    title=f"Review Ready: {ticket.jira_key}",
                    message=f"Changes implemented for '{ticket.title}'. Coding agent completed task in sandbox.",
                    status="pending",
                    action_url=f"/tickets/{ticket.id}"
                )
                session.add(notif)
                session.commit()

                pr_url = pr_info.get("html_url") if pr_info else None
                update_run_status_sync(
                    run_id,
                    status="COMPLETED",
                    pr_url=pr_url,
                    metrics={
                        "agent_name": effective_agent,
                        "task_id": task_id,
                        "session_id": harness_result.session_id,
                        "has_remote_jules": has_remote_jules,
                        "summary_changes": harness_result.summary_changes
                    }
                )
                append_event_sync(
                    run_id=run_id,
                    event_type="RUN_COMPLETED",
                    payload={
                        "status": "COMPLETED",
                        "pr_url": pr_url,
                        "session_id": harness_result.session_id,
                        "summary": harness_result.summary_changes
                    },
                    level="INFO"
                )

                return {
                    "success": True,
                    "status": "review_ready",
                    "task_id": task_id,
                    "run_id": str(run_id) if run_id else None,
                    "ticket_id": ticket.id,
                    "work_log_id": work_log.id,
                    "summary_changes": harness_result.summary_changes,
                    "preparations_result": prep_result,
                    "git_diff": harness_result.git_diff,
                    "workspace_orchestration": handoff_record,
                    "pull_request": pr_info,
                    "session_id": harness_result.session_id
                }

        finally:
            session.close()

    def merge_and_cleanup_branch(self, ticket_id: int) -> Dict[str, Any]:
        """
        Merges branch, cleans up coding agent container environment,
        and pushes completion update to Jira.
        """
        session = self.get_session()
        try:
            ticket = session.query(Ticket).filter(Ticket.id == ticket_id).first()
            if not ticket:
                return {"success": False, "error": "Ticket not found"}

            project = ticket.project

            # 1. Clean up container sandbox via Coding Agent Orchestrator
            if ticket.branch_name:
                self.coding_orchestrator.cleanup_container(project.key, ticket.branch_name)

            # 2. Push update to Jira
            self.jira_service.mark_ticket_merged(ticket.jira_key)

            # 3. Mark ticket merged in database
            ticket.status = "merged"
            session.commit()

            logger.info("Successfully merged ticket %s and cleaned up container sandbox.", ticket.jira_key)
            return {"success": True, "ticket_id": ticket.id, "status": "merged"}
        finally:
            session.close()

workflow_engine = HephaestusWorkflowEngine()
