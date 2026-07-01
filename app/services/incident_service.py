from datetime import datetime, timezone
import cognee
from app.action.generate_rca import generate_rca
from app.action.recall_similar_incidents import recall_similar_incidents
from app.action.remember_incident import remember_incident
from app.schemas.incident import (
    Incident,
    IncidentCreate,
    IncidentDetailResponse,
    IncidentResolveRequest,
)
from cognee.modules.engine.operations.setup import setup

_store: list[dict] = []
_counter = 0


async def create_incident(data: IncidentCreate) -> IncidentDetailResponse:
    global _counter

    _counter += 1

    incident = Incident(
        id=_counter,
        title=data.title,
        severity=data.severity,
        service=data.service,
        environment=data.environment,
        symptoms=data.symptoms,
        status="open",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await setup()

    similar_incidents = await recall_similar_incidents(incident)
    rca = await generate_rca(incident, similar_incidents)

    incident.root_cause = rca.root_cause

    record = {
        **incident.model_dump(),
        "confidence": rca.confidence,
        "recommended_fix": rca.recommended_fix,
        "first_action": rca.first_action,
        "recalled_from": similar_incidents,
    }

    _store.append(record)

    await remember_incident(incident)

    return IncidentDetailResponse(**record)


async def resolve_incident(
    incident_id: int, data: IncidentResolveRequest
) -> IncidentDetailResponse | None:
    for record in _store:
        if record["id"] != incident_id:
            continue

        record["status"] = "resolved"
        record["fix_applied"] = data.fix_applied
        record["updated_at"] = datetime.now(timezone.utc)

        incident = Incident(**record)
        await remember_incident(incident)
        await cognee.improve()

        return IncidentDetailResponse(**record)

    return None


def get_incident(incident_id: int) -> IncidentDetailResponse | None:
    for record in _store:
        if record["id"] == incident_id:
            return IncidentDetailResponse(**record)
    return None


def list_incidents() -> list[IncidentDetailResponse]:
    return [IncidentDetailResponse(**r) for r in _store]
