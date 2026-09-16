from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Boolean
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import relationship
from backend.database.connection import Base

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    key = Column(String(50), nullable=False, unique=True, index=True)
    jira_key = Column(String(50), nullable=True)
    jira_ticket_key = Column(String(50), nullable=True)
    repo_url = Column(Text, nullable=True)
    base_image = Column(String(255), default="python:3.12-slim")
    system_prompt_additions = Column(Text, default="")
    color = Column(String(30), default="#3B82F6")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    tickets = relationship("Ticket", back_populates="project", cascade="all, delete-orphan")
    work_logs = relationship("WorkLog", back_populates="project", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessage", back_populates="project", cascade="all, delete-orphan")
    notifications = relationship("AgentNotification", back_populates="project", cascade="all, delete-orphan")

class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    jira_key = Column(String(50), nullable=False, index=True)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    branch_name = Column(String(255), nullable=True)
    container_id = Column(String(255), nullable=True)
    image_id = Column(String(255), nullable=True)
    status = Column(String(50), default="pending") # pending, in_progress, paused_waiting_input, review_ready, merged, failed
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="tickets")
    work_logs = relationship("WorkLog", back_populates="ticket", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessage", back_populates="ticket", cascade="all, delete-orphan")
    notifications = relationship("AgentNotification", back_populates="ticket", cascade="all, delete-orphan")

class WorkLog(Base):
    __tablename__ = "work_logs"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    prompt_raw = Column(Text, nullable=False)
    prompt_processed = Column(Text, nullable=False)
    staged_files = Column(JSONB, default=list)
    status = Column(String(50), default="completed") # in_progress, paused_waiting_input, completed, failed
    summary_changes = Column(Text, nullable=True)
    what_was_wrong = Column(Text, nullable=True)
    what_was_done = Column(Text, nullable=True)
    user_check_items = Column(JSONB, default=list)
    git_diff = Column(Text, nullable=True)
    full_log = Column(Text, nullable=True)
    tsv = Column(TSVECTOR, nullable=True)

    project = relationship("Project", back_populates="work_logs")
    ticket = relationship("Ticket", back_populates="work_logs")

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    sender = Column(String(50), nullable=False) # user, agent, system
    message_type = Column(String(50), default="question") # question, answer, notification, approval_request, log
    content = Column(Text, nullable=False)
    metadata_json = Column("metadata", JSONB, default=dict)
    status = Column(String(50), default="pending") # pending, answered, acknowledged
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    tsv = Column(TSVECTOR, nullable=True)

    project = relationship("Project", back_populates="chat_messages")
    ticket = relationship("Ticket", back_populates="chat_messages")

class AgentNotification(Base):
    __tablename__ = "agent_notifications"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(50), nullable=False) # needs_input, completed, failed, info
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(50), default="pending") # pending, approved, denied, resolved
    action_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    project = relationship("Project", back_populates="notifications")
    ticket = relationship("Ticket", back_populates="notifications")
