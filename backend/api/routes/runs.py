import uuid
import asyncio
import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func
from fastapi.responses import StreamingResponse

from backend.db.models import Run, RunEvent
from backend.db.service import async_session_factory

router = APIRouter(prefix="/api", tags=["runs"])

@router.get("/runs")
async def list_runs(
    jira_key: Optional[str] = None,
    status: Optional[str] = None,
    target_platform: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    if not async_session_factory:
        raise HTTPException(500, "Database session factory not configured.")
    async with async_session_factory() as session:
        stmt = select(Run).order_by(Run.created_at.desc())
        if jira_key:
            stmt = stmt.where(Run.jira_key == jira_key)
        if status:
            stmt = stmt.where(Run.status == status)
        if target_platform:
            stmt = stmt.where(Run.target_platform == target_platform)

        stmt = stmt.limit(limit).offset(offset)
        result = await session.execute(stmt)
        runs = result.scalars().all()
        return [
            {
                "id": str(r.id),
                "jira_key": r.jira_key,
                "status": r.status,
                "target_platform": r.target_platform,
                "created_at": r.created_at
            } for r in runs
        ]

@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID):
    if not async_session_factory:
        raise HTTPException(500, "Database session factory not configured.")
    async with async_session_factory() as session:
        run = await session.get(Run, run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        return {
            "id": str(run.id),
            "jira_key": run.jira_key,
            "status": run.status,
            "target_platform": run.target_platform,
            "branch_name": run.branch_name,
            "prep_summary": run.prep_summary,
            "metrics": run.metrics,
            "error_message": run.error_message,
            "created_at": run.created_at,
            "updated_at": run.updated_at
        }

@router.get("/runs/{run_id}/events")
async def get_run_events(run_id: uuid.UUID):
    if not async_session_factory:
        raise HTTPException(500, "Database session factory not configured.")
    async with async_session_factory() as session:
        stmt = select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.timestamp.asc())
        result = await session.execute(stmt)
        events = result.scalars().all()
        return [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "level": e.level,
                "payload": e.payload,
                "timestamp": e.timestamp
            } for e in events
        ]

@router.get("/runs/{run_id}/stream")
async def stream_run_events(run_id: uuid.UUID):
    async def event_generator():
        # A simple SSE generator that polls the database for new events
        last_timestamp = None
        while True:
            if not async_session_factory:
                break
            async with async_session_factory() as session:
                stmt = select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.timestamp.asc())
                if last_timestamp:
                    stmt = stmt.where(RunEvent.timestamp > last_timestamp)
                result = await session.execute(stmt)
                events = result.scalars().all()

                for e in events:
                    data = {
                        "id": str(e.id),
                        "event_type": e.event_type,
                        "level": e.level,
                        "payload": e.payload,
                        "timestamp": str(e.timestamp)
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                    last_timestamp = e.timestamp

            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/stats")
async def get_stats():
    if not async_session_factory:
        raise HTTPException(500, "Database session factory not configured.")
    async with async_session_factory() as session:
        total_runs = await session.execute(select(func.count(Run.id)))
        total_runs = total_runs.scalar()

        success_runs = await session.execute(select(func.count(Run.id)).where(Run.status == "COMPLETED"))
        success_runs = success_runs.scalar()

        return {
            "total_runs": total_runs,
            "success_rate": (success_runs / total_runs * 100) if total_runs > 0 else 0
        }
