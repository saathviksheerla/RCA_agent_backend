import json
from unittest.mock import AsyncMock

import pytest

from app.action.generate_rca import generate_rca, llm
from app.schemas.incident import RCAResponse


class FakeLLMResponse:
    def __init__(self, content: str):
        self.content = content


VALID_RCA_JSON = json.dumps(
    {
        "root_cause": "Connection pool exhausted due to unbounded retry loop",
        "confidence": 85,
        "recommended_fix": "Add exponential backoff and pool size limits",
        "first_action": "Restart the affected service instances",
        "recalled_from": ["Historical incident A"],
    }
)


@pytest.mark.asyncio
async def test_generate_rca_returns_parsed_response_on_valid_json(
    make_incident, monkeypatch
):
    mock_ainvoke = AsyncMock(return_value=FakeLLMResponse(VALID_RCA_JSON))
    monkeypatch.setattr(type(llm), "ainvoke", mock_ainvoke)

    incident = make_incident()
    result = await generate_rca(incident, ["Historical Incident: past outage"])

    assert isinstance(result, RCAResponse)
    assert result.confidence == 85
    assert "Connection pool" in result.root_cause

    prompt_arg = mock_ainvoke.call_args[0][0][0]["content"]
    assert incident.title in prompt_arg
    assert incident.service in prompt_arg
    assert "past outage" in prompt_arg


@pytest.mark.asyncio
async def test_generate_rca_with_no_similar_incidents_still_prompts(
    make_incident, monkeypatch
):
    mock_ainvoke = AsyncMock(return_value=FakeLLMResponse(VALID_RCA_JSON))
    monkeypatch.setattr(type(llm), "ainvoke", mock_ainvoke)

    incident = make_incident()
    await generate_rca(incident, [])

    prompt_arg = mock_ainvoke.call_args[0][0][0]["content"]
    assert "No similar incidents found" in prompt_arg


@pytest.mark.asyncio
async def test_generate_rca_raises_on_malformed_json(make_incident, monkeypatch):
    """Documents a known gap: generate_rca has no error handling around
    json.loads, so a non-JSON LLM response crashes with an unhandled
    JSONDecodeError instead of a clean HTTP error."""
    mock_ainvoke = AsyncMock(return_value=FakeLLMResponse("not valid json"))
    monkeypatch.setattr(type(llm), "ainvoke", mock_ainvoke)

    incident = make_incident()
    with pytest.raises(json.JSONDecodeError):
        await generate_rca(incident, [])
