import time
from datetime import datetime, timezone
import cognee
from fastapi import BackgroundTasks
from sqlalchemy import select
from app.perf import Timer
from app.database import async_session
from app.models.incident import IncidentModel
from app.action.generate_rca import generate_rca
from app.action.recall_similar_incidents import recall_similar_incidents
from app.action.remember_incident import remember_incident
from app.schemas.incident import (
    Incident,
    IncidentCreate,
    IncidentDetailResponse,
    IncidentResolveRequest,
    RecalledFromItem,
)


def _score_recalled(text: str, service: str, environment: str) -> int:
    score = 0
    for line in text.split("\n"):
        if line.startswith("Service:") and service in line:
            score += 2
        elif line.startswith("Environment:") and environment in line:
            score += 1
    return score


def _parse_recalled(text: str) -> RecalledFromItem:
    title = symptom = service = fix = ""
    for line in text.split("\n"):
        if line.startswith("Title:"):
            title = line.split(":", 1)[1].strip()
        elif line.startswith("Symptoms:"):
            symptom = line.split(":", 1)[1].strip()
        elif line.startswith("Service:"):
            service = line.split(":", 1)[1].strip()
        elif line.startswith("Fix Applied:"):
            fix = line.split(":", 1)[1].strip()
    return RecalledFromItem(
        incident_title=title,
        symptom=symptom,
        service=service,
        fix=fix or "Not resolved yet",
    )


async def create_incident(
    data: IncidentCreate, background_tasks: BackgroundTasks
) -> IncidentDetailResponse:
    now = datetime.now(timezone.utc)

    incident = Incident(
        id=0,
        title=data.title,
        severity=data.severity,
        service=data.service,
        environment=data.environment,
        symptoms=data.symptoms,
        status="open",
        created_at=now,
        updated_at=now,
    )

    _t_total = time.perf_counter()
    with Timer("recall_total"):
        similar_incidents = await recall_similar_incidents(incident)
    similar_incidents = [
        t
        for t in similar_incidents
        if _score_recalled(t, incident.service, incident.environment) > 0
    ]
    similar_incidents.sort(
        key=lambda t: _score_recalled(t, incident.service, incident.environment),
        reverse=True,
    )
    with Timer("generate_rca_total"):
        rca = await generate_rca(incident, similar_incidents)

    incident.root_cause = rca.root_cause

    recalled_items = [_parse_recalled(s) for s in similar_incidents]

    with Timer("db_total"):
        async with async_session() as session:
            db_incident = IncidentModel(
                title=data.title,
                severity=data.severity.value,
                service=data.service,
                environment=data.environment,
                symptoms=data.symptoms,
                status="open",
                root_cause=rca.root_cause,
                confidence=rca.confidence,
                recommended_fix=rca.recommended_fix,
                first_action=rca.first_action,
                recalled_from=[r.model_dump() for r in recalled_items],
                created_at=now,
                updated_at=now,
            )
            session.add(db_incident)
            with Timer("db_commit(acquire+insert+commit)"):
                await session.commit()
            with Timer("db_refresh"):
                await session.refresh(db_incident)

    # Index into memory after the response is sent: it's the slow part (~minutes
    # of graph extraction) and recall already ran above, so the client shouldn't
    # wait on it. `await`-ing remember_incident here would still block the
    # response no matter what flag we pass it, since await always waits for the
    # coroutine to finish.
    background_tasks.add_task(remember_incident, incident, True)
    logger_perf_total = (time.perf_counter() - _t_total) * 1000
    from app.perf import logger as _plog
    _plog.info("[PERF] %-30s %10.1f ms", "CREATE_INCIDENT_TOTAL", logger_perf_total)

    return IncidentDetailResponse(
        id=db_incident.id,
        title=db_incident.title,
        severity=db_incident.severity,
        service=db_incident.service,
        environment=db_incident.environment,
        symptoms=db_incident.symptoms,
        status=db_incident.status,
        root_cause=db_incident.root_cause,
        confidence=db_incident.confidence,
        recommended_fix=db_incident.recommended_fix,
        first_action=db_incident.first_action,
        recalled_from=recalled_items,
        created_at=db_incident.created_at,
        updated_at=db_incident.updated_at,
    )


async def resolve_incident(
    incident_id: int, data: IncidentResolveRequest, background_tasks: BackgroundTasks
) -> IncidentDetailResponse | None:
    async with async_session() as session:
        result = await session.execute(
            select(IncidentModel).where(IncidentModel.id == incident_id)
        )
        db_incident = result.scalar_one_or_none()
        if db_incident is None:
            return None

        db_incident.status = "resolved"
        db_incident.root_cause = data.confirmed_root_cause
        db_incident.fix_applied = data.fix_applied
        db_incident.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(db_incident)

    incident = Incident(
        id=db_incident.id,
        title=db_incident.title,
        severity=db_incident.severity,
        service=db_incident.service,
        environment=db_incident.environment,
        symptoms=db_incident.symptoms,
        status=db_incident.status,
        created_at=db_incident.created_at,
        updated_at=db_incident.updated_at,
        root_cause=db_incident.root_cause,
        fix_applied=db_incident.fix_applied,
    )
    background_tasks.add_task(remember_incident, incident)
    background_tasks.add_task(cognee.improve)

    return IncidentDetailResponse(
        id=db_incident.id,
        title=db_incident.title,
        severity=db_incident.severity,
        service=db_incident.service,
        environment=db_incident.environment,
        symptoms=db_incident.symptoms,
        status=db_incident.status,
        root_cause=db_incident.root_cause,
        confidence=db_incident.confidence,
        recommended_fix=db_incident.recommended_fix,
        first_action=db_incident.first_action,
        fix_applied=db_incident.fix_applied,
        recalled_from=(
            [RecalledFromItem(**r) for r in db_incident.recalled_from]
            if db_incident.recalled_from
            else []
        ),
        created_at=db_incident.created_at,
        updated_at=db_incident.updated_at,
    )


async def get_incident(incident_id: int) -> IncidentDetailResponse | None:
    async with async_session() as session:
        result = await session.execute(
            select(IncidentModel).where(IncidentModel.id == incident_id)
        )
        db_incident = result.scalar_one_or_none()
        if db_incident is None:
            return None
        return IncidentDetailResponse(
            id=db_incident.id,
            title=db_incident.title,
            severity=db_incident.severity,
            service=db_incident.service,
            environment=db_incident.environment,
            symptoms=db_incident.symptoms,
            status=db_incident.status,
            root_cause=db_incident.root_cause,
            confidence=db_incident.confidence,
            recommended_fix=db_incident.recommended_fix,
            first_action=db_incident.first_action,
            fix_applied=db_incident.fix_applied,
            recalled_from=(
                [RecalledFromItem(**r) for r in db_incident.recalled_from]
                if db_incident.recalled_from
                else []
            ),
            created_at=db_incident.created_at,
            updated_at=db_incident.updated_at,
        )


async def list_incidents() -> list[IncidentDetailResponse]:
    async with async_session() as session:
        result = await session.execute(
            select(IncidentModel).order_by(IncidentModel.created_at.desc())
        )
        rows = result.scalars().all()
        return [
            IncidentDetailResponse(
                id=row.id,
                title=row.title,
                severity=row.severity,
                service=row.service,
                environment=row.environment,
                symptoms=row.symptoms,
                status=row.status,
                root_cause=row.root_cause,
                confidence=row.confidence,
                recommended_fix=row.recommended_fix,
                first_action=row.first_action,
                fix_applied=row.fix_applied,
                recalled_from=(
                    [RecalledFromItem(**r) for r in row.recalled_from]
                    if row.recalled_from
                    else []
                ),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]
