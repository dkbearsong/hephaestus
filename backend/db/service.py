import uuid
from typing import Optional, Dict, Any, Union
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, update
from backend.config import DATABASE_URL
from backend.db.models import Run, RunEvent
from backend.database.connection import SessionLocal
import logging

logger = logging.getLogger("db_service")

# Construct async connection string
async_db_url = DATABASE_URL
if async_db_url.startswith("postgresql://"):
    async_db_url = async_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

async_session_factory = None
try:
    if "pytest" not in __import__("sys").modules:
        engine = create_async_engine(
            async_db_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=False
        )
        async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
except Exception as e:
    logger.error(f"Failed to create async engine: {e}")


def _normalize_platform(target_platform: Optional[str]) -> str:
    """Normalizes target_platform string to the target_platform_enum values."""
    plat = str(target_platform or "").upper().strip()
    if plat in ("GOOGLE_JULES", "JULES"):
        return "GOOGLE_JULES"
    elif plat in ("CODEX_CLOUD", "OPENAI_CODEX_CLOUD", "CODEX"):
        return "CODEX_CLOUD"
    return "LOCAL_CONTAINER"


def _normalize_mode(mode: Optional[str]) -> str:
    """Normalizes run mode string to run_mode_enum values."""
    m = str(mode or "").upper().replace("-", "_").strip()
    if "NEW" in m:
        return "PROMPT_NEW"
    return "PROMPT"


def _to_uuid(val: Union[str, uuid.UUID, None]) -> Optional[uuid.UUID]:
    if val is None:
        return None
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val))
    except Exception:
        return None


# ==============================================================================
# Synchronous Database Operations (for sync workflow engine & preprocessor)
# ==============================================================================

def create_run_sync(
    jira_key: str,
    mode: str,
    target_platform: str,
    status: str = "QUEUED",
    branch_name: Optional[str] = None,
    prep_summary: Optional[Dict[str, Any]] = None,
    metrics: Optional[Dict[str, Any]] = None,
    run_id: Optional[Union[str, uuid.UUID]] = None
) -> Optional[uuid.UUID]:
    """Synchronously creates a new Run record in the database."""
    clean_platform = _normalize_platform(target_platform)
    clean_mode = _normalize_mode(mode)
    assigned_id = _to_uuid(run_id) or uuid.uuid4()

    try:
        session = SessionLocal()
        try:
            new_run = Run(
                id=assigned_id,
                jira_key=jira_key,
                mode=clean_mode,
                target_platform=clean_platform,
                status=status,
                branch_name=branch_name,
                prep_summary=prep_summary,
                metrics=metrics
            )
            session.add(new_run)
            session.commit()
            return new_run.id
        finally:
            session.close()
    except Exception as e:
        logger.error(f"[db_service] Error creating run (sync): {e}")
        return None


def update_run_status_sync(
    run_id: Union[str, uuid.UUID],
    status: str,
    **kwargs
) -> bool:
    """Synchronously updates run status and optional fields (e.g. branch_name, pr_url, metrics)."""
    run_uuid = _to_uuid(run_id)
    if not run_uuid:
        return False

    try:
        session = SessionLocal()
        try:
            run = session.get(Run, run_uuid)
            if not run:
                return False
            run.status = status
            for k, v in kwargs.items():
                if hasattr(run, k):
                    if k in ("metrics", "prep_summary") and getattr(run, k) and isinstance(getattr(run, k), dict) and isinstance(v, dict):
                        merged = dict(getattr(run, k))
                        merged.update(v)
                        setattr(run, k, merged)
                    else:
                        setattr(run, k, v)
            session.commit()
            return True
        finally:
            session.close()
    except Exception as e:
        logger.error(f"[db_service] Error updating run status (sync) for {run_id}: {e}")
        return False


def append_event_sync(
    run_id: Union[str, uuid.UUID],
    event_type: str,
    payload: Any,
    level: str = "INFO"
) -> Optional[uuid.UUID]:
    """Synchronously appends a telemetry event to run_events."""
    run_uuid = _to_uuid(run_id)
    if not run_uuid:
        return None

    clean_payload = payload if isinstance(payload, dict) else {"data": payload}

    try:
        session = SessionLocal()
        try:
            new_event = RunEvent(
                id=uuid.uuid4(),
                run_id=run_uuid,
                event_type=event_type,
                level=level,
                payload=clean_payload
            )
            session.add(new_event)
            session.commit()
            return new_event.id
        finally:
            session.close()
    except Exception as e:
        logger.error(f"[db_service] Error appending event (sync) to run {run_id}: {e}")
        return None


# ==============================================================================
# Asynchronous Database Operations (for FastAPI endpoints & async runners)
# ==============================================================================

async def create_run(
    jira_key: str,
    mode: str,
    target_platform: str,
    status: str = "QUEUED",
    branch_name: Optional[str] = None,
    prep_summary: Optional[Dict[str, Any]] = None,
    metrics: Optional[Dict[str, Any]] = None,
    run_id: Optional[Union[str, uuid.UUID]] = None
) -> Optional[uuid.UUID]:
    if not async_session_factory:
        return create_run_sync(jira_key, mode, target_platform, status, branch_name, prep_summary, metrics, run_id)
    try:
        clean_platform = _normalize_platform(target_platform)
        clean_mode = _normalize_mode(mode)
        assigned_id = _to_uuid(run_id) or uuid.uuid4()

        async with async_session_factory() as session:
            new_run = Run(
                id=assigned_id,
                jira_key=jira_key,
                mode=clean_mode,
                target_platform=clean_platform,
                status=status,
                branch_name=branch_name,
                prep_summary=prep_summary,
                metrics=metrics
            )
            session.add(new_run)
            await session.commit()
            return new_run.id
    except Exception as e:
        logger.error(f"Error creating run: {e}")
        return None


async def update_run_status(run_id: Union[str, uuid.UUID], status: str, **kwargs) -> bool:
    if not async_session_factory:
        return update_run_status_sync(run_id, status, **kwargs)
    try:
        run_uuid = _to_uuid(run_id)
        if not run_uuid:
            return False

        async with async_session_factory() as session:
            run = await session.get(Run, run_uuid)
            if not run:
                return False
            run.status = status
            for k, v in kwargs.items():
                if hasattr(run, k):
                    if k in ("metrics", "prep_summary") and getattr(run, k) and isinstance(getattr(run, k), dict) and isinstance(v, dict):
                        merged = dict(getattr(run, k))
                        merged.update(v)
                        setattr(run, k, merged)
                    else:
                        setattr(run, k, v)
            await session.commit()
            return True
    except Exception as e:
        logger.error(f"Error updating run status for {run_id}: {e}")
        return False


async def append_event(
    run_id: Union[str, uuid.UUID],
    event_type: str,
    payload: Any,
    level: str = "INFO"
) -> Optional[uuid.UUID]:
    if not async_session_factory:
        return append_event_sync(run_id, event_type, payload, level)
    try:
        run_uuid = _to_uuid(run_id)
        if not run_uuid:
            return None

        clean_payload = payload if isinstance(payload, dict) else {"data": payload}

        async with async_session_factory() as session:
            new_event = RunEvent(
                id=uuid.uuid4(),
                run_id=run_uuid,
                event_type=event_type,
                level=level,
                payload=clean_payload
            )
            session.add(new_event)
            await session.commit()
            return new_event.id
    except Exception as e:
        logger.error(f"Error appending event to run {run_id}: {e}")
        return None
