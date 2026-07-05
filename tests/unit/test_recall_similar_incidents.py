from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.action.recall_similar_incidents import recall_similar_incidents
from cognee.modules.retrieval.exceptions.exceptions import NoDataError


class FakeRecallItem:
    def __init__(self, text: str):
        self.text = text


@pytest.mark.asyncio
async def test_recall_returns_texts_on_success(make_incident, monkeypatch):
    fake_results = [FakeRecallItem("Historical incident A"), FakeRecallItem("Historical incident B")]
    mock_recall = AsyncMock(return_value=fake_results)
    monkeypatch.setattr("app.action.recall_similar_incidents.cognee.recall", mock_recall)

    incident = make_incident()
    result = await recall_similar_incidents(incident)

    assert result == ["Historical incident A", "Historical incident B"]
    call_kwargs = mock_recall.call_args.kwargs
    assert incident.service in call_kwargs["query_text"]
    assert incident.environment in call_kwargs["query_text"]


@pytest.mark.asyncio
async def test_recall_returns_empty_list_on_no_data_error(make_incident, monkeypatch):
    mock_recall = AsyncMock(side_effect=NoDataError())
    monkeypatch.setattr("app.action.recall_similar_incidents.cognee.recall", mock_recall)

    incident = make_incident()
    result = await recall_similar_incidents(incident)

    assert result == []


@pytest.mark.asyncio
async def test_recall_wraps_other_exceptions_as_500(make_incident, monkeypatch):
    mock_recall = AsyncMock(side_effect=RuntimeError("cognee unreachable"))
    monkeypatch.setattr("app.action.recall_similar_incidents.cognee.recall", mock_recall)

    incident = make_incident()
    with pytest.raises(HTTPException) as exc_info:
        await recall_similar_incidents(incident)

    assert exc_info.value.status_code == 500
    assert "cognee unreachable" in exc_info.value.detail
