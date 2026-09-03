import uuid
import logging
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
        target_agent: Optional[str] = None
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

        # Step 1: Prompt extraction (includes optional <|preparations|>)
        is_prompt, prompt_meta = self.prompt_extractor.extract_prompt(comment_text, task_id)
        if not is_prompt:
            logger.info("Comment does not contain trigger prefix. Skipping.")
            return {"success": False, "reason": "No prompt trigger prefix found"}

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
            prep_result = self.preparations_runner.run_preparations(
                task_id=task_id,
                preparations_prompt=effective_prep,
                staging_dir=staging_dir
            )
            logger.info("[Workflow Pipeline] Preparations step completed. End-of-Token received: %s. Continuing to Coding Agent stage.",
                        prep_result.get("end_token_received"))

        # Determine project key
        proj_key = project_key_hint or jira_issue_key.split("-")[0] if "-" in jira_issue_key else "DEFAULT"
        is_new_proj = prompt_meta.get("is_new_project", False)

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

            branch_name = f"hephaestus/{jira_issue_key.lower()}-{task_id}"
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

            # Step 5: Execute with Coding Agent Orchestrator
            # (which validates prompt, initiates container environment, and executes task)
            active_harness = self.harness
            container_info = {
                "project_key": project.key,
                "branch_name": ticket.branch_name,
                "repo_url": project.repo_url,
                "staged_files": staged_files,
                "is_new_project": is_new_proj,
                "preparations_result": prep_result
            }

            if hasattr(self, "_harness") and self._harness is not None:
                # Test stub/mock or specific harness override
                harness_result = self._harness.run_task(
                    prompt=cleaned_prompt,
                    container_info=container_info,
                    project_config={"name": project.name, "key": project.key, "branch_name": ticket.branch_name},
                    system_prompt_additions=project.system_prompt_additions
                )
            else:
                # Dispatch via CodingAgentOrchestrator
                harness_result = self.coding_orchestrator.execute_workflow(
                    prompt=cleaned_prompt,
                    project_key=project.key,
                    branch_name=ticket.branch_name,
                    repo_url=project.repo_url,
                    staged_files=staged_files,
                    is_new_project=is_new_proj,
                    system_prompt_additions=project.system_prompt_additions,
                    preparations_result=prep_result,
                    target_agent=target_agent
                )

            ticket.container_id = f"container_{project.key}_{ticket.branch_name}"
            ticket.image_id = f"sandbox_{target_agent or 'active'}"
            session.commit()

            # Step 6: Handle Result (Paused vs Completed)
            now = datetime.now(timezone.utc)
            if harness_result.status == "paused_waiting_input":
                ticket.status = "paused_waiting_input"

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
                    "ticket_id": ticket.id,
                    "question": harness_result.question_for_user,
                    "preparations_result": prep_result
                }

            else: # completed
                ticket.status = "review_ready"

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

                return {
                    "success": True,
                    "status": "review_ready",
                    "ticket_id": ticket.id,
                    "work_log_id": work_log.id,
                    "summary_changes": harness_result.summary_changes,
                    "preparations_result": prep_result,
                    "git_diff": harness_result.git_diff
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
