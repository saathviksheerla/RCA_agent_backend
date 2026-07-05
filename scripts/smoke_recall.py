"""Smoke-test recall quality after the embedding switch.

Mirrors the app's real path: store incidents via cognee.remember() using the
same text format as app/action/remember_incident.py, then recall with the same
call as app/action/recall_similar_incidents.py (CHUNKS, only_context, top_k=5).

We store two unrelated incidents plus one payment incident, then query with a
NEW payment incident. A working setup should recall the payment incident, not
the unrelated ones.

Usage:
    uv run python scripts/smoke_recall.py
"""

import asyncio

from dotenv import load_dotenv

load_dotenv()

import cognee  # noqa: E402
from cognee import SearchType  # noqa: E402
from cognee.modules.engine.operations.setup import setup  # noqa: E402

SEED = [
    """Title: API gateway timeout on payment service
Service: payment-gateway
Environment: production
Severity: high
Symptoms: users getting 504 errors when checking out. p99 latency spiked from 200ms to 12s. error rate jumped to 34%.""",
    """Title: Kafka consumer lag spike on billing-events topic
Service: billing-worker
Environment: production
Severity: medium
Symptoms: consumer lag grew to 2M messages, downstream invoices delayed by 40 minutes.""",
    """Title: CDN cache invalidation failure
Service: cdn-edge
Environment: production
Severity: high
Symptoms: stale assets served to users. cache purge requests failing with 502.""",
]

QUERY = (
    "cloud incident on service payment-gateway in production. "
    "symptoms: transactions failing with 502 after new deployment. latency spikes from 100ms to 8s."
)


async def main() -> None:
    print("Running Cognee setup (creates tables, like the app's lifespan)...")
    await setup()

    print("Storing seed incidents...")
    for text in SEED:
        await cognee.remember(text, self_improvement=False)

    print("\nRecalling for a NEW payment-gateway incident...\n")
    results = await cognee.recall(
        query_text=QUERY,
        query_type=SearchType.CHUNKS,
        only_context=True,
        top_k=5,
    )

    if not results:
        print("!! No results returned.")
        return

    for i, item in enumerate(results, 1):
        text = getattr(item, "text", str(item))
        first_line = text.strip().splitlines()[0] if text.strip() else "(empty)"
        print(f"[{i}] {first_line}")

    top = getattr(results[0], "text", "")
    print("\nPASS" if "payment-gateway" in top else "\nWEAK: top result is not the payment-gateway incident")


if __name__ == "__main__":
    asyncio.run(main())
