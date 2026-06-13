import os
import sys
from pathlib import Path

# Use an isolated SQLite DB for the whole test session, set before app imports
os.environ["DATABASE_URL"] = "sqlite:///./test_cti.db"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["SCHEDULER_ENABLED"] = "false"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import pytest_asyncio


@pytest.fixture(scope="session")
def db_engine():
    from app.db.session import engine
    from app.db.base import Base
    import app.models  # noqa: F401 — register all ORM classes
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()
    for suffix in ("", "-wal", "-shm"):
        p = Path(f"./test_cti.db{suffix}")
        if p.exists():
            p.unlink()


@pytest.fixture()
def db(db_engine):
    from app.db.session import SessionLocal
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest_asyncio.fixture(scope="session")
async def client(db_engine):
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture(scope="session")
async def auth_headers(client):
    resp = await client.post("/api/auth/login", json={"username": "admin", "password": "wraith"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
