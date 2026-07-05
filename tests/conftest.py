"""Shared fixtures. Sets dummy env vars before any `app.*` module is imported,
so module-level side effects (getpass prompt in generate_rca.py, DATABASE_URL
construction in database.py) don't block or crash test collection."""
import os

from dotenv import load_dotenv

load_dotenv()  # picks up real LLM_API_KEY / Cognee creds for the functional suite, if present

os.environ.setdefault("LLM_API_KEY", "test-dummy-key")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USERNAME", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as database


def pytest_addoption(parser):
    parser.addoption(
        "--functional",
        action="store_true",
        default=False,
        help="run gated functional tests that call real Cognee Cloud + Groq",
    )


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def test_session_factory(test_engine, monkeypatch):
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(database, "async_session", session_factory)
    monkeypatch.setattr(
        "app.services.incident_service.async_session", session_factory
    )
    return session_factory


@pytest_asyncio.fixture
async def client(test_session_factory):
    from app.app import app as fastapi_app

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def make_incident():
    from datetime import datetime, timezone
    from app.schemas.incident import Incident, Severity

    def _make(**overrides):
        now = datetime.now(timezone.utc)
        defaults = dict(
            id=1,
            title="Checkout latency spike",
            severity=Severity.HIGH,
            service="payment-service",
            environment="production",
            symptoms="connection pool exhausted",
            status="open",
            created_at=now,
            updated_at=now,
        )
        defaults.update(overrides)
        return Incident(**defaults)

    return _make
