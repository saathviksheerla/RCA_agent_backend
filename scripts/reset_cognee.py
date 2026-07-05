"""Reset Cognee's memory stores.

Run this AFTER changing the embedding model or EMBEDDING_DIMENSIONS. Cognee's
pgvector collection is created with a fixed vector width (was 2048, now 1536),
so the old collection must be dropped and recreated at the new dimension.

prune_system() defaults: graph=True, vector=True, metadata=False, cache=True.
We pass metadata=True for a full clean slate (datasets + pipeline state too).

SAFE: this only clears Cognee's own graph/vector/metadata tables in Neon.
Your app's `incidents` table (SQLAlchemy) is NOT a Cognee table and is untouched.

Usage:
    uv run python scripts/reset_cognee.py
"""

import asyncio

from dotenv import load_dotenv

load_dotenv()  # load .env from project root before importing cognee

import cognee  # noqa: E402


async def main() -> None:
    await cognee.prune.prune_system(metadata=True)
    print("Cognee memory reset. Vector collection will be recreated at the new dimension on next remember().")


if __name__ == "__main__":
    asyncio.run(main())
