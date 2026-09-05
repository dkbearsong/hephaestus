import json
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from backend.workflows.task_graph import workflow_engine
from backend.coding_agents.orchestrator import coding_agent_orchestrator
from backend.database.search import search_full_text
from backend.database.connection import get_db, SessionLocal
from backend.database.models import Project, Ticket, WorkLog, ChatMessage, AgentNotification
from backend.jira_service.client import jira_service
from backend.config import JIRA_WEBHOOK_SECRET, get_prompt_output_dir
from backend.watcher.webhook_watcher import (
    webhook_watcher,
    FormattedWebhookPayload,
    WebhookPayloadFormatter,
    WebhookSecretVerificationError
)

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hephaestus.api")

# Connect webhook watcher to workflow engine
webhook_watcher.pipeline_engine = workflow_engine

app = FastAPI(title="Hephaestus Coding Agent Harness Backend", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class WebhookPayload(BaseModel):
    comment_text: str
    jira_issue_key: str
    summary: Optional[str] = ""
    project_key: Optional[str] = ""
    target_agent: Optional[str] = None

class MergeRequest(BaseModel):
    ticket_id: int

class ChatRequest(BaseModel):
    ticket_id: int
    content: str
    sender: str = "user"

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "hephaestus_python_core",
        "version": "2.0.0",
        "active_coding_agent": coding_agent_orchestrator.get_agent().display_name
    }

@app.get("/api/coding-agents")
def list_coding_agents():
    """Returns the catalog of 6 supported containerized coding agent orchestrators."""
    return {
        "active_agent": coding_agent_orchestrator.get_agent().agent_id,
        "agents": coding_agent_orchestrator.list_supported_agents()
    }

@app.post("/api/pipeline/webhook")
async def process_webhook(payload: WebhookPayload, request: Request):
    headers = dict(request.headers)
    try:
        formatted = webhook_watcher.receive_webhook(payload.model_dump(), headers=headers)
    except WebhookSecretVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    if not formatted.is_ai_trigger:
        return {"success": False, "reason": "No prompt trigger prefix found"}
    result = workflow_engine.process_webhook_prompt(
        comment_text=payload.comment_text,
        jira_issue_key=formatted.jira_issue_key,
        issue_summary=formatted.summary,
        project_key_hint=formatted.project_key,
        preparations=formatted.preparations,
        target_agent=payload.target_agent
    )
    return result

@app.post("/")
@app.post("/api/webhooks/jira")
@app.post("/webhook")
@app.post("/api/webhook")
async def receive_jira_webhook(request: Request):
    """Direct Jira Cloud webhook receiver endpoint with secret verification."""
    raw_body = await request.body()
    try:
        raw_payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    headers = dict(request.headers)
    try:
        formatted = webhook_watcher.receive_webhook(raw_payload, headers=headers, raw_body=raw_body)
    except WebhookSecretVerificationError as exc:
        logger.warning("Rejecting unauthorized webhook: %s", exc)
        raise HTTPException(status_code=401, detail=str(exc))

    if not formatted.is_ai_trigger:
        return {"success": True, "message": "Ignored: No prompt tag", "payload": formatted.model_dump()}
    result = webhook_watcher.dispatch_to_pipeline(formatted)

    ws_orch = result.get("workspace_orchestration") if isinstance(result, dict) else None
    if ws_orch:
        logger.info(
            "\n" + "=" * 70 + "\n"
            f"🚀 [WEBHOOK PROCESSED & WORKSPACE ORCHESTRATED]\n"
            f"• Ticket    : {formatted.jira_issue_key}\n"
            f"• Workspace : {ws_orch.get('working_directory')}\n"
            f"• Branch    : {ws_orch.get('branch_name')}\n"
            f"• Platform  : {ws_orch.get('target_platform')}\n"
            f"• Ready     : {ws_orch.get('ready_for_execution')}\n"
            + "=" * 70
        )

    return {"success": True, "pipeline_result": result, "formatted": formatted.model_dump()}

@app.get("/api/webhooks/test-jira-push")
def test_jira_push_info():
    """Returns configuration diagnostics and instructions for testing pushes from Jira."""
    return {
        "status": "ready",
        "description": "Hephaestus Manual Jira Push Test Route",
        "prompt_save_directory": str(get_prompt_output_dir()),
        "secret_configured": bool(JIRA_WEBHOOK_SECRET),
        "supported_coding_agents": [a["agent_id"] for a in coding_agent_orchestrator.list_supported_agents()],
        "instructions": (
            "Configure Jira Cloud Webhook to send 'comment_created' or 'issue_updated' events. "
            "A comment starting with '<|prompt|>' will trigger Preparations (LangGraph) -> "
            "Coding Agent Orchestrator (Google Jules, Grok Build, OpenAI Codex, Docker Sandbox Claude/Codex, Devin, OpenHands)."
        )
    }

@app.post("/api/webhooks/test-jira-push")
async def manual_test_jira_push(request: Request):
    """
    Dedicated endpoint where users can manually test webhook pushes from their linked Jira site.
    Performs full tag parsing, verifies whether comment begins with <|prompt|>,
    dispatches through Preparations LangGraph and Coding Agent Orchestrator,
    and returns detailed test diagnostics.
    """
    raw_body = await request.body()
    try:
        raw_payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    headers = dict(request.headers)
    target_agent = raw_payload.get("target_agent") or request.query_params.get("agent")
    
    # Optional secret verification for manual tests
    secret_valid = False
    has_secret_header = "x-hub-signature-256" in headers or "x-hub-signature" in headers or "x-webhook-secret" in headers
    if has_secret_header:
        try:
            formatted = webhook_watcher.receive_webhook(raw_payload, headers=headers, raw_body=raw_body)
            secret_valid = True
        except WebhookSecretVerificationError as exc:
            raise HTTPException(status_code=401, detail=f"Webhook secret verification failed: {exc}")
    else:
        formatted = WebhookPayloadFormatter.format_payload(raw_payload)

    # Verification 1: Check if pushed comment begins with <|prompt|>
    if not formatted.is_ai_trigger:
        return {
            "test_status": "ignored",
            "pushed_through_pipeline": False,
            "reason": "Comment does not begin with <|prompt|> or <|prompt-new|>",
            "received_comment": formatted.raw_comment,
            "detected_tag": formatted.prompt_tag,
            "jira_issue_key": formatted.jira_issue_key
        }

    # Verification 2: Run pipeline
    if target_agent:
        pipeline_result = workflow_engine.process_webhook_prompt(
            comment_text=formatted.in_memory_comment,
            jira_issue_key=formatted.jira_issue_key,
            issue_summary=formatted.summary,
            project_key_hint=formatted.project_key,
            preparations=formatted.preparations,
            target_agent=target_agent
        )
    else:
        pipeline_result = webhook_watcher.dispatch_to_pipeline(formatted)

    save_base_dir = get_prompt_output_dir()

    return {
        "test_status": "success",
        "pushed_through_pipeline": True,
        "jira_issue_key": formatted.jira_issue_key,
        "prompt_tag": formatted.prompt_tag,
        "has_preparations": formatted.has_preparations,
        "preparations": formatted.preparations,
        "prompt_instructions": formatted.prompt_instructions,
        "prompt_save_base_directory": str(save_base_dir),
        "target_agent": target_agent or "default_from_preferences",
        "pipeline_result": pipeline_result,
        "secret_verified": secret_valid
    }

@app.post("/api/pipeline/merge")
def merge_branch(req: MergeRequest):
    result = workflow_engine.merge_and_cleanup_branch(req.ticket_id)
    return result

@app.get("/api/search")
def search(q: str = Query(..., min_length=1), project_id: Optional[int] = None, limit: int = 20):
    return search_full_text(q, project_id=project_id, limit=limit)

@app.get("/api/jira/issue/{issue_key}")
def get_jira_issue(issue_key: str):
    return jira_service.get_issue_details(issue_key)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
