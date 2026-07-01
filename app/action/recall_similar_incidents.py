




from cognee import cognee
from fastapi import HTTPException
from app.schemas.incident import Incident


async def recall_similar_incidents(
    incident: Incident,
) -> list[str]:
    query = f"""
Find previous cloud incidents similar to:
Service: {incident.service}
Environment: {incident.environment}
Symptoms: {incident.symptoms}
Return incidents with similar symptoms,
root causes, or resolutions.
""".strip()
    
    try:

        results = await cognee.recall(
            query_text=query,
            only_context=True,
        )
        similar_incidents = []

        for item in results:
            similar_incidents.append(item.text)
        
        return similar_incidents
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to recall similar incidents: {str(e)}",
        )