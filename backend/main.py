from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from backend.workflows.task_graph import workflow_engine
from backend.database.search import search_full_text
from backend.database.connection import get_db, SessionLocal
from backend.database.models import Project, Ticket, WorkLog, ChatMessage, AgentNotification
from backend.jira_service.client import jira_service
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hephaestus.api")

app = FastAPI(title="Hephaestus Coding Agent Harness Backend", version="1.0.0")

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

class MergeRequest(BaseModel):
    ticket_id: int

class ChatRequest(BaseModel):
    ticket_id: int
    content: str
    sender: str = "user"

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "hephaestus_python_core"}

@app.post("/api/pipeline/webhook")
def process_webhook(payload: WebhookPayload):
    result = workflow_engine.process_webhook_prompt(
        comment_text=payload.comment_text,
        jira_issue_key=payload.jira_issue_key,
        issue_summary=payload.summary,
        project_key_hint=payload.project_key
    )
    return result

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
