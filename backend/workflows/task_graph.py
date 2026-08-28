import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from backend.database.connection import SessionLocal
from backend.database.models import Project, Ticket, WorkLog, ChatMessage, AgentNotification
from backend.jira_service.client import jira_service
from backend.preprocessor.prompt_extractor import prompt_extractor
from backend.preprocessor.file_gatherer import file_gatherer
from backend.docker_manager.container_service import docker_manager
from backend.harness import get_active_harness

logger = logging.getLogger("hephaestus.workflows")

class HephaestusWorkflowEngine:
    def process_webhook_prompt(
        self,
        comment_text: str,
        jira_issue_key: str,
        issue_summary: str = "",
        project_key_hint: str = ""
    ) -> Dict[str, Any]:
        """
        Main workflow pipeline triggered by incoming Jira Webhook.
        1. Check trigger prefix (<|prompt|> or <|prompt-new|>)
        2. Remove trigger label in Jira so further updates won't re-fire
        3. Extract prompt and save to .md
        4. Gather & stage files (<|files|>) and rewrite container paths
        5. Check / create Docker container for the branch
        6. Feed into active Coding Harness
        7. Pause if question/external access needed (triggers RED notification),
           otherwise checkpoint container & save WorkLog (triggers YELLOW notification).
        """
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        logger.info("Processing incoming webhook for issue %s (Task ID: %s)", jira_issue_key, task_id)

        # Step 1: Prompt extraction
        is_prompt, prompt_meta = prompt_extractor.extract_prompt(comment_text, task_id)
        if not is_prompt:
            logger.info("Comment does not contain trigger prefix. Skipping.")
            return {"success": False, "reason": "No prompt trigger prefix found"}

        # Step 2: Remove trigger label in Jira to prevent infinite webhook loops
        jira_service.remove_trigger_label(jira_issue_key)

        # Step 3 & 4: Gather & stage files
        staging_dir = prompt_meta["task_staging_dir"]
        prompt_file = prompt_meta["prompt_file_path"]
        stage_res = file_gatherer.extract_and_stage_files(prompt_file, staging_dir)
        staged_files = stage_res.get("staged_files", [])
        cleaned_prompt = stage_res.get("updated_prompt", prompt_meta["cleaned_prompt"])

        # Determine project key
        proj_key = project_key_hint or jira_issue_key.split("-")[0] if "-" in jira_issue_key else "DEFAULT"
        is_new_proj = prompt_meta.get("is_new_project", False)

        session = SessionLocal()
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

            # Step 5: Check or create branch Docker container
            container_info = docker_manager.ensure_branch_container(
                project_key=project.key,
                branch_name=ticket.branch_name,
                repo_url=project.repo_url,
                base_image=project.base_image,
                staged_files=staged_files,
                is_new_project=is_new_proj
            )
            ticket.container_id = container_info.get("container_name")
            ticket.image_id = container_info.get("checkpoint_tag")
            session.commit()

            # Step 6: Feed prompt into Coding Harness
            harness = get_active_harness()
            harness_result = harness.run_task(
                prompt=cleaned_prompt,
                container_info=container_info,
                project_config={"name": project.name, "key": project.key},
                system_prompt_additions=project.system_prompt_additions
            )

            # Step 7: Handle Result (Paused vs Completed)
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
                    "question": harness_result.question_for_user
                }

            else: # completed
                # Checkpoint & spin down container
                if ticket.container_id and ticket.image_id:
                    docker_manager.spin_down_and_checkpoint(ticket.container_id, ticket.image_id)

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
                    message=f"Changes implemented for '{ticket.title}'. Container spun down and ready for review.",
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
                    "summary_changes": harness_result.summary_changes
                }

        finally:
            session.close()

    def merge_and_cleanup_branch(self, ticket_id: int) -> Dict[str, Any]:
        """
        Merges branch, deletes Docker container and checkpoint images,
        and pushes completion update to Jira.
        """
        session = SessionLocal()
        try:
            ticket = session.query(Ticket).filter(Ticket.id == ticket_id).first()
            if not ticket:
                return {"success": False, "error": "Ticket not found"}

            project = ticket.project

            # 1. Delete Docker container & checkpoint images
            if ticket.branch_name:
                docker_manager.delete_on_merge(project.key, ticket.branch_name)

            # 2. Push update to Jira
            jira_service.mark_ticket_merged(ticket.jira_key)

            # 3. Mark ticket merged in database
            ticket.status = "merged"
            session.commit()

            logger.info("Successfully merged ticket %s and cleaned up container resources.", ticket.jira_key)
            return {"success": True, "ticket_id": ticket.id, "status": "merged"}
        finally:
            session.close()

workflow_engine = HephaestusWorkflowEngine()
