"""
Prefect 3.x Workflow Flows for Hephaestus Task Orchestration
"""
from prefect import task, flow
from backend.workflows.task_graph import workflow_engine

@task(name="process_jira_webhook_task", retries=2)
def process_webhook_task(comment_text: str, jira_issue_key: str, summary: str = "", project_key: str = ""):
    return workflow_engine.process_webhook_prompt(
        comment_text=comment_text,
        jira_issue_key=jira_issue_key,
        issue_summary=summary,
        project_key_hint=project_key
    )

@task(name="merge_and_cleanup_branch_task")
def merge_and_cleanup_task(ticket_id: int):
    return workflow_engine.merge_and_cleanup_branch(ticket_id)

@flow(name="hephaestus_webhook_flow")
def run_hephaestus_webhook_flow(comment_text: str, jira_issue_key: str, summary: str = "", project_key: str = ""):
    return process_webhook_task(comment_text, jira_issue_key, summary, project_key)

@flow(name="hephaestus_merge_flow")
def run_hephaestus_merge_flow(ticket_id: int):
    return merge_and_cleanup_task(ticket_id)
