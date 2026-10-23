import os
import sys
import tempfile
from pathlib import Path

import pytest

scratch = Path(tempfile.mkdtemp(prefix="sqe-platform-tests-"))
os.environ.update(
    APP_ENV="development",
    APP_SECRET="test-secret-with-more-than-thirty-two-characters",
    DATABASE_URL=f"sqlite:///{scratch / 'test.db'}",
    STORAGE_DRIVER="local",
    STORAGE_PATH=str(scratch / "files"),
    WORKFLOW_DRIVER="local",
    DEV_PASSWORD="P@ssw0rd2026",
    DEV_EMAIL="sqe@bic.local",
    DEV_ORGANIZATION="sqe",
)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import Base, engine  # noqa: E402 — isolated environment must be set first.
from app.configuration.initialize import initialize_development  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    initialize_development()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def signed(client):
    response = client.post(
        "/api/auth/login",
        json={
            "organization": "sqe",
            "email": "sqe@bic.local",
            "password": "P@ssw0rd2026",
        },
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return client
