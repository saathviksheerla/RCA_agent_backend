import json
from unittest.mock import AsyncMock

import pytest

from app.action.generate_rca import llm

VALID_RCA_JSON = json.dumps(
    {
        "root_cause": "Connection pool exhausted",
        "confidence": 80,
        "recommended_fix": "Scale the RDS instance",
        "first_action": "Restart affected pods",
        "recalled_from": [],
    }
)


class FakeRecallItem:
    def __init__(self, text: str):
        self.text = text


class FakeLLMResponse:
    def __init__(self, content: str):
        self.content = content


def patch_external_services(monkeypatch, recall_texts=None, rca_json=VALID_RCA_JSON):
    fake_recall_items = [FakeRecallItem(t) for t in (recall_texts or [])]
    monkeypatch.setattr(
        "app.action.recall_similar_incidents.cognee.recall",
        AsyncMock(return_value=fake_recall_items),
    )
    monkeypatch.setattr(
        "app.action.remember_incident.cognee.remember", AsyncMock(return_value=None)
    )
    monkeypatch.setattr("app.services.incident_service.cognee.improve", AsyncMock(return_value=None))
    monkeypatch.setattr(type(llm), "ainvoke", AsyncMock(return_value=FakeLLMResponse(rca_json)))


VALID_PAYLOAD = {
    "title": "Checkout latency spike",
    "severity": "high",
    "service": "payment-service",
    "environment": "production",
    "symptoms": "connection pool exhausted",
}


@pytest.mark.asyncio
async def test_create_incident_returns_201_with_full_detail(client, monkeypatch):
    patch_external_services(monkeypatch)

    resp = await client.post("/incidents", json=VALID_PAYLOAD)

    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == VALID_PAYLOAD["title"]
    assert body["status"] == "open"
    assert body["root_cause"] == "Connection pool exhausted"
    assert body["confidence"] == 80
    assert body["recommended_fix"] == "Scale the RDS instance"
    assert body["recalled_from"] == []
    assert "id" in body and "created_at" in body


@pytest.mark.asyncio
async def test_create_incident_parses_recalled_from_similar_incidents(client, monkeypatch):
    recall_text = (
        "Title: Past outage\n"
        "Service: payment-service\n"
        "Environment: production\n"
        "Symptoms: pool exhaustion\n"
        "Fix Applied: scaled RDS"
    )
    patch_external_services(monkeypatch, recall_texts=[recall_text])

    resp = await client.post("/incidents", json=VALID_PAYLOAD)

    assert resp.status_code == 201
    recalled = resp.json()["recalled_from"]
    assert len(recalled) == 1
    assert recalled[0]["incident_title"] == "Past outage"
    assert recalled[0]["fix"] == "scaled RDS"


@pytest.mark.asyncio
async def test_create_incident_missing_required_field_returns_422(client, monkeypatch):
    patch_external_services(monkeypatch)
    payload = dict(VALID_PAYLOAD)
    del payload["service"]

    resp = await client.post("/incidents", json=payload)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_incident_invalid_severity_returns_422(client, monkeypatch):
    patch_external_services(monkeypatch)
    payload = dict(VALID_PAYLOAD, severity="catastrophic")

    resp = await client.post("/incidents", json=payload)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_resolve_incident_success(client, monkeypatch):
    patch_external_services(monkeypatch)
    create_resp = await client.post("/incidents", json=VALID_PAYLOAD)
    incident_id = create_resp.json()["id"]

    resolve_payload = {
        "confirmed_root_cause": "Confirmed: pool exhaustion",
        "fix_applied": "Increased pool size",
    }
    resp = await client.post(f"/incidents/{incident_id}/resolve", json=resolve_payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "resolved"
    assert body["root_cause"] == "Confirmed: pool exhaustion"
    assert body["fix_applied"] == "Increased pool size"


@pytest.mark.asyncio
async def test_resolve_incident_calls_cognee_improve(client, monkeypatch):
    patch_external_services(monkeypatch)
    improve_mock = AsyncMock(return_value=None)
    monkeypatch.setattr("app.services.incident_service.cognee.improve", improve_mock)

    create_resp = await client.post("/incidents", json=VALID_PAYLOAD)
    incident_id = create_resp.json()["id"]

    await client.post(
        f"/incidents/{incident_id}/resolve",
        json={"confirmed_root_cause": "x", "fix_applied": "y"},
    )

    improve_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_unknown_incident_returns_404(client, monkeypatch):
    patch_external_services(monkeypatch)

    resp = await client.post(
        "/incidents/9999/resolve",
        json={"confirmed_root_cause": "x", "fix_applied": "y"},
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_incident_success(client, monkeypatch):
    patch_external_services(monkeypatch)
    create_resp = await client.post("/incidents", json=VALID_PAYLOAD)
    incident_id = create_resp.json()["id"]

    resp = await client.get(f"/incidents/{incident_id}")

    assert resp.status_code == 200
    assert resp.json()["id"] == incident_id


@pytest.mark.asyncio
async def test_get_unknown_incident_returns_404(client, monkeypatch):
    patch_external_services(monkeypatch)

    resp = await client.get("/incidents/9999")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_incidents_empty(client, monkeypatch):
    patch_external_services(monkeypatch)

    resp = await client.get("/incidents")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_incidents_ordered_by_created_at_desc(client, monkeypatch):
    patch_external_services(monkeypatch)

    first = await client.post("/incidents", json=VALID_PAYLOAD)
    second = await client.post(
        "/incidents", json=dict(VALID_PAYLOAD, title="Second incident")
    )

    resp = await client.get("/incidents")

    assert resp.status_code == 200
    titles = [item["title"] for item in resp.json()]
    assert titles == ["Second incident", "Checkout latency spike"]


@pytest.mark.asyncio
async def test_create_incident_rca_failure_leaves_no_db_row(client, monkeypatch):
    """generate_rca raises before the DB commit in create_incident, so no
    partial row should be persisted."""
    monkeypatch.setattr(
        "app.action.recall_similar_incidents.cognee.recall",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(type(llm), "ainvoke", AsyncMock(side_effect=RuntimeError("groq down")))

    with pytest.raises(RuntimeError):
        await client.post("/incidents", json=VALID_PAYLOAD)

    patch_external_services(monkeypatch)
    resp = await client.get("/incidents")
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_incident_remember_failure_returns_500_but_db_row_persists(
    client, monkeypatch
):
    """Documents a real inconsistency: remember_incident() is called after the
    DB commit in create_incident, so a Cognee failure surfaces as a 500 to the
    client even though the incident row was already persisted."""
    monkeypatch.setattr(
        "app.action.recall_similar_incidents.cognee.recall",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(type(llm), "ainvoke", AsyncMock(return_value=FakeLLMResponse(VALID_RCA_JSON)))
    monkeypatch.setattr(
        "app.action.remember_incident.cognee.remember",
        AsyncMock(side_effect=RuntimeError("cognee down")),
    )

    create_resp = await client.post("/incidents", json=VALID_PAYLOAD)
    assert create_resp.status_code == 500

    patch_external_services(monkeypatch)
    resp = await client.get("/incidents")
    assert len(resp.json()) == 1
