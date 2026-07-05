"""Accuracy probe: show EXACTLY what cognee.recall returns for the app's queries.

Prints the raw result objects, their count, and how the app's _parse_recalled /
_score_recalled interpret them — so we can see why the wrong incident surfaces.

Usage: uv run python scripts/recall_probe.py
"""

import asyncio

from dotenv import load_dotenv
load_dotenv("/Users/vijender/Desktop/RCA/.env")

import cognee  # noqa: E402
from cognee import SearchType  # noqa: E402
from cognee.modules.engine.operations.setup import setup  # noqa: E402
from app.services.incident_service import _parse_recalled, _score_recalled  # noqa: E402

# (query, service, environment) mirroring how the app builds the recall query.
CASES = [
    ("payment-gateway", "production",
     "transactions failing with 502 after new deployment. latency spikes from 100ms to 8s."),
    ("billing-worker", "production",
     "kafka consumer lag grew to 2M messages, downstream invoices delayed by 40 minutes."),
]


async def probe(service, environment, symptoms, only_context):
    query = f"cloud incident on service {service} in {environment}. symptoms: {symptoms}"
    print("\n" + "=" * 78)
    print(f"QUERY service={service} | only_context={only_context}")
    print("=" * 78)
    results = await cognee.recall(
        query_text=query, query_type=SearchType.CHUNKS,
        only_context=only_context, top_k=5, auto_route=False,
    )
    print(f"len(results) = {len(results)}")
    for i, r in enumerate(results):
        text = getattr(r, "text", str(r))
        print(f"\n--- result[{i}]  type={type(r).__name__}  len(text)={len(text)} ---")
        print(text[:1500])
    print("\n>>> What the APP does: [item.text for item in results] -> _parse_recalled per item")
    for r in results:
        text = getattr(r, "text", str(r))
        item = _parse_recalled(text)
        score = _score_recalled(text, service, environment)
        print(f"   parsed_title={item.incident_title!r}  service={item.service!r}  score={score}")


async def main():
    await setup()
    for service, env, sym in CASES:
        await probe(service, env, sym, only_context=True)
    print("\n\n########## COMPARISON: only_context=False ##########")
    for service, env, sym in CASES:
        await probe(service, env, sym, only_context=False)


if __name__ == "__main__":
    asyncio.run(main())
