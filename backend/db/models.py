import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Enum, DateTime, ForeignKey, text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Run(Base):
    __tablename__ = "runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    jira_key = Column(String(32), index=True)
    mode = Column(Enum("PROMPT", "PROMPT_NEW", name="run_mode_enum"))
    target_platform = Column(Enum("GOOGLE_JULES", "CODEX_CLOUD", "LOCAL_CONTAINER", name="target_platform_enum"))
    status = Column(Enum("QUEUED", "PREPARING", "CODING", "AWAITING_CI", "COMPLETED", "FAILED", name="run_status_enum"), default="QUEUED")
    branch_name = Column(String(255), nullable=True)
    pr_url = Column(String, nullable=True)
    prep_summary = Column(JSONB, nullable=True)
    metrics = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), server_default=text("now()"))

    events = relationship("RunEvent", back_populates="run", cascade="all, delete-orphan", order_by="RunEvent.timestamp")

class RunEvent(Base):
    __tablename__ = "run_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), index=True, nullable=False)
    event_type = Column(String(64), nullable=False)
    level = Column(Enum("INFO", "WARNING", "ERROR", name="log_level_enum"), default="INFO")
    payload = Column(JSONB, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=text("now()"))

    run = relationship("Run", back_populates="events")

    __table_args__ = (
        Index("idx_run_events_payload", payload, postgresql_using="gin"),
    )
