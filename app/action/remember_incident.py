import logging

from cognee import cognee
from app.schemas.incident import Incident
from app.perf import Timer

logger = logging.getLogger(__name__)


def incident_to_memory(incident: Incident) -> str:
    memory = f"""
Title: {incident.title}
Service: {incident.service}
Environment: {incident.environment}
Severity: {incident.severity.value}
Symptoms: {incident.symptoms}
""".strip()

    if incident.root_cause:
        memory += f"\nRoot Cause: {incident.root_cause}"

    if incident.fix_applied:
        memory += f"\nFix Applied: {incident.fix_applied}"

    return memory


async def remember_incident(incident: Incident, background: bool = False) -> bool:
    """Store the incident in Cognee's memory.

    With background=True, indexing (the slow graph-extraction pipeline) runs
    without blocking the caller. A failure here is logged, not raised: the
    incident is already persisted in Postgres, so a memory-write failure must
    not turn a successful create into a 500.
    """
    memory_text = incident_to_memory(incident)
    try:
        with Timer(f"cognee.remember(bg={background})"):
            await cognee.remember(
                memory_text, self_improvement=False, run_in_background=background
            )
        return True
    except Exception as e:
        logger.warning("Failed to store incident in memory: %s", e)
        return False
