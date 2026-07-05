from cognee import cognee, SearchType
from cognee.modules.retrieval.exceptions.exceptions import NoDataError
from fastapi import HTTPException

from app.schemas.incident import Incident
from app.perf import Timer

async def recall_similar_incidents(incident: Incident) -> list[str]:
    query = f"cloud incident on service {incident.service} in {incident.environment}. symptoms: {incident.symptoms}"
    try:
        with Timer("cognee.recall"):
            results = await cognee.recall(
                query_text=query,
                query_type=SearchType.CHUNKS,
                # only_context=False returns each matching chunk as a SEPARATE,
                # ranked result. only_context=True concatenates all 5 chunks into
                # ONE blob, which _parse_recalled then mangles (it reads the last
                # value of each field across all incidents) — the cause of the
                # "Kafka query recalled a Payment incident" bug.
                only_context=False,
                top_k=5,
                # We force CHUNKS, so skip the query-router classification step
                # (it otherwise runs and is discarded — see logs "Router override").
                auto_route=False,
            )
        return [item.text for item in results]
    except NoDataError:
        return []
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to recall similar incidents: {str(e)}",
        )