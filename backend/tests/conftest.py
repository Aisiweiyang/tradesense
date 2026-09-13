"""Shared pytest fixtures: isolated in-memory SQLite DB + authenticated API client."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

# Test settings BEFORE app modules import config
os.environ["DATABASE_URL"] = "sqlite://"  # in-memory; tests never touch a file DB
os.environ["SEED_DEMO_DATA"] = "0"


@pytest.fixture(scope="session")
def db_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from app.models import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(db_engine):
    """Fresh session per test, rolled back afterwards."""
    connection = db_engine.connect()
    transaction = connection.begin()
    from sqlalchemy.orm import sessionmaker

    TestSession = sessionmaker(bind=connection, autoflush=False, future=True)
    session = TestSession()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def org(db):
    from app.models import Organization, User
    from app.security import hash_password

    org = Organization(name="测试公司")
    db.add(org)
    db.flush()
    user = User(org_id=org.id, email="owner@test.cn", name="测试员",
                password_hash=hash_password("password123"))
    db.add(user)
    db.commit()
    return org


@pytest.fixture()
def other_org(db):
    """Second organization for isolation tests."""
    from app.models import Organization, User
    from app.security import hash_password

    org = Organization(name="另一家公司")
    db.add(org)
    db.flush()
    user = User(org_id=org.id, email="owner2@test.cn", name="他司测试员",
                password_hash=hash_password("password123"))
    db.add(user)
    db.commit()
    return org


@pytest.fixture()
def client(db, org):
    """FastAPI TestClient sharing the test session; auth via real login flow."""
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    app.state.test_db = db  # exposed for tests that need to seed directly
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def auth_headers(client, email: str = "owner@test.cn", password: str = "password123") -> dict:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
