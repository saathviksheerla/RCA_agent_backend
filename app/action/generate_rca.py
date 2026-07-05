import os
import json

from fastapi import HTTPException
from pydantic import ValidationError
from langchain_openai import ChatOpenAI
from app.schemas.incident import Incident, RCAResponse

# Track LLM_MODEL from .env; strip the "openai/" litellm prefix Cognee uses,
# since langchain's ChatOpenAI wants the bare model name (e.g. "gpt-4o-mini").
_model = os.getenv("LLM_MODEL", "openai/gpt-4o-mini").split("/", 1)[-1]

# Fail fast with a clear message instead of hanging/crashing obscurely.
_api_key = os.environ.get("LLM_API_KEY")
if not _api_key:
    raise RuntimeError("LLM_API_KEY is not set. Add it to your .env.")

llm = ChatOpenAI(
    model=_model,
    api_key=_api_key,
    temperature=1,
    max_retries=2,
    # Force valid JSON so json.loads() below can't choke on stray prose/markdown.
    model_kwargs={"response_format": {"type": "json_object"}},
)


async def generate_rca(incident: Incident, similar_incidents: list[str]) -> RCAResponse:
    similar_text = ("\n".join(f"Historical Incident: {s}" for s in similar_incidents) or "No similar incidents found")
    prompt = f"""You are a Senior Cloud Reliability Engineer performing Root Cause Analysis.

##Current Incident

Title: {incident.title}

Service: {incident.service}

Environments: {incident.environment}

Severity: {incident.severity}

Symptons: {incident.symptoms}

## Similar Historical Incidents

{similar_text}

##Task

Analyze the current incident using the similar historical Incidents as context.

Return a JSON object with exactly these fields:
- "root_cause": str = what caused this incident
- "confidence": int = your confidence in this analysis (0-100)
- "recommended_fix": str = how to resolve this incident
- "first_action": str = the immediate step to take
- "recalled_from": list[str] = the historical incidents that informed your analysis (copy relevant fields)

Return ONLY valid JSON. No markdown. No explanation."""
    response = await llm.ainvoke([
        {"role": "user", "content": prompt}
    ])
    raw = response.content
    try:
        final_data = json.loads(raw)
        return RCAResponse(**final_data)
    except (json.JSONDecodeError, ValidationError, TypeError) as e:
        raise HTTPException(
            status_code=502,
            detail="RCA generation returned an invalid response, please try again.",
        ) from e
