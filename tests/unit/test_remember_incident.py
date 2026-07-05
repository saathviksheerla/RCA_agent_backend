from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.action.remember_incident import incident_to_memory, remember_incident


class TestIncidentToMemory:
    def test_base_fields_always_present(self, make_incident):
        incident = make_incident(root_cause=None, fix_applied=None)
        memory = incident_to_memory(incident)
        assert "Title: Checkout latency spike" in memory
        assert "Service: payment-service" in memory
        assert "Environment: production" in memory
        assert "Severity: high" in memory
        assert "Symptoms: connection pool exhausted" in memory
        assert "Root Cause:" not in memory
        assert "Fix Applied:" not in memory

    def test_root_cause_appended_when_present(self, make_incident):
        incident = make_incident(root_cause="pool exhaustion", fix_applied=None)
        memory = incident_to_memory(incident)
        assert "Root Cause: pool exhaustion" in memory
        assert "Fix Applied:" not in memory

    def test_fix_applied_appended_when_present(self, make_incident):
        incident = make_incident(root_cause="pool exhaustion", fix_applied="scaled db")
        memory = incident_to_memory(incident)
        assert "Root Cause: pool exhaustion" in memory
        assert "Fix Applied: scaled db" in memory


@pytest.mark.asyncio
async def test_remember_incident_success(make_incident, monkeypatch):
    mock_remember = AsyncMock(return_value=None)
    monkeypatch.setattr("app.action.remember_incident.cognee.remember", mock_remember)

    incident = make_incident()
    await remember_incident(incident)

    mock_remember.assert_awaited_once()
    call_kwargs = mock_remember.call_args
    assert call_kwargs.kwargs.get("self_improvement") is False


@pytest.mark.asyncio
async def test_remember_incident_wraps_exception_as_500(make_incident, monkeypatch):
    mock_remember = AsyncMock(side_effect=RuntimeError("cognee down"))
    monkeypatch.setattr("app.action.remember_incident.cognee.remember", mock_remember)

    incident = make_incident()
    with pytest.raises(HTTPException) as exc_info:
        await remember_incident(incident)

    assert exc_info.value.status_code == 500
    assert "cognee down" in exc_info.value.detail
