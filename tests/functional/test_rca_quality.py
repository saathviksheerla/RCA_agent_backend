"""Gated tests against real Cognee Cloud + real Groq. Skipped by default.

Run with: pytest tests/functional -v -m functional --functional
(requires real LLM_API_KEY / Cognee credentials loaded from .env)

Cognee Cloud is a persistent remote store with no rollback available, so each
run uses a uniquely-tagged incident title to avoid colliding with data from
previous runs. Treat this suite as best-effort/non-deterministic — it is
meant to be run manually before a demo, not in CI.
"""
import json
import os
import uuid

import pytest

pytestmark = pytest.mark.functional

RUN_TAG = uuid.uuid4().hex[:8]

REQUIRES_LIVE_CREDS = not os.getenv("LLM_API_KEY") or os.getenv("LLM_API_KEY") == "test-dummy-key"


skip_reason = "Set a real LLM_API_KEY (and Cognee Cloud credentials) in the environment to run functional tests"


@pytest.fixture(autouse=True)
def _require_functional_flag(request):
    if not request.config.getoption("--functional", default=False):
        pytest.skip("pass --functional to run gated real-service tests")
    if REQUIRES_LIVE_CREDS:
        pytest.skip(skip_reason)


@pytest.mark.asyncio
async def test_recall_finds_seeded_incident_with_different_wording(make_incident):
    from app.action.remember_incident import remember_incident
    from app.action.recall_similar_incidents import recall_similar_incidents

    seeded = make_incident(
        id=1,
        title=f"[{RUN_TAG}] Payment gateway timeouts under load",
        service="payment-service",
        environment="production",
        symptoms="Requests to the payment gateway start timing out during peak traffic",
        root_cause="Thread pool exhaustion in the payment gateway client",
        fix_applied="Increased thread pool size and added circuit breaker",
    )
    await remember_incident(seeded)

    new_incident = make_incident(
        id=2,
        title=f"[{RUN_TAG}] Checkout requests hanging during high load",
        service="payment-service",
        environment="production",
        symptoms="Users report checkout hangs and eventually errors out when traffic is high",
    )

    results = await recall_similar_incidents(new_incident)

    assert results, "expected recall to return at least one similar incident"
    assert any("thread pool" in r.lower() or "timeout" in r.lower() for r in results), (
        f"expected recall results to reference the seeded incident, got: {results}"
    )


@pytest.mark.asyncio
async def test_generate_rca_produces_well_formed_and_plausible_output(make_incident):
    from app.action.generate_rca import generate_rca, llm

    incident = make_incident(
        title=f"[{RUN_TAG}] Database connections exhausted",
        service="orders-service",
        symptoms="Application logs show 'too many connections' errors from Postgres, "
        "orders API returning 503s",
    )
    similar = [
        "Historical Incident: Title: Prior DB outage\nService: orders-service\n"
        "Symptoms: connection pool exhausted\nFix Applied: increased max_connections and added pgbouncer"
    ]

    rca = await generate_rca(incident, similar)

    assert rca.root_cause.strip()
    assert rca.recommended_fix.strip()
    assert rca.first_action.strip()
    assert 0 <= rca.confidence <= 100

    judge_prompt = f"""You are grading an incident root-cause-analysis for plausibility.

Incident symptoms: {incident.symptoms}
Proposed root cause: {rca.root_cause}
Proposed fix: {rca.recommended_fix}

On a scale of 1-5 (5 = highly plausible and relevant, 1 = nonsensical or irrelevant),
score how plausible this root cause and fix are given the symptoms.
Return ONLY a single integer 1-5, nothing else."""
    judge_response = await llm.ainvoke([{"role": "user", "content": judge_prompt}])
    score = int("".join(c for c in judge_response.content if c.isdigit())[:1] or "0")

    assert score >= 3, (
        f"LLM-judge scored RCA plausibility as {score}/5 "
        f"(root_cause={rca.root_cause!r}, fix={rca.recommended_fix!r})"
    )
