import uuid
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, update
from backend.config import DATABASE_URL
from backend.db.models import Run, RunEvent
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

async def create_run(
    jira_key: str,
    mode: str,
    target_platform: str,
    status: str = "QUEUED",
    branch_name: Optional[str] = None
) -> Optional[uuid.UUID]:
    if not async_session_factory: return None
    try:
        async with async_session_factory() as session:
            new_run = Run(
                jira_key=jira_key,
                mode=mode,
                target_platform=target_platform,
                status=status,
                branch_name=branch_name
            )
            session.add(new_run)
            await session.commit()
            return new_run.id
    except Exception as e:
        logger.error(f"Error creating run: {e}")
        return None

async def update_run_status(run_id: uuid.UUID, status: str, **kwargs) -> bool:
    if not async_session_factory: return False
    try:
        async with async_session_factory() as session:
            stmt = update(Run).where(Run.id == run_id).values(status=status, **kwargs)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating run status for {run_id}: {e}")
        return False

async def append_event(run_id: uuid.UUID, event_type: str, payload: Dict[str, Any], level: str = "INFO") -> Optional[uuid.UUID]:
    if not async_session_factory: return None
    try:
        async with async_session_factory() as session:
            new_event = RunEvent(
                run_id=run_id,
                event_type=event_type,
                level=level,
                payload=payload
            )
            session.add(new_event)
            await session.commit()
            return new_event.id
    except Exception as e:
        logger.error(f"Error appending event to run {run_id}: {e}")
        return None
