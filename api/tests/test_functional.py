"""
Functional tests — happy-path coverage for core API endpoints.

MinIO is replaced with a MagicMock; no live services are required.
All credentials (usernames and passwords) are loaded from .env via dotenv_values.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from main import app  # noqa: E402

_ENV = dotenv_values(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_minio_mock() -> MagicMock:
    m = MagicMock()
    m.bucket_exists.return_value = True
    m.put_object.return_value = None
    m.list_objects.return_value = iter([])
    return m


@pytest.fixture()
def client():
    mock = _make_minio_mock()
    with patch("main.get_minio", return_value=mock), patch("main.ensure_buckets"):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c, mock


@pytest.fixture(autouse=True)
def _reset_rate_window():
    import main
    main._query_window.clear()
    yield
    main._query_window.clear()


# ---------------------------------------------------------------------------
# Functional tests
# ---------------------------------------------------------------------------

def test_health_returns_200(client):
    c, _ = client
    r = c.get("/health")
    assert r.status_code == 200
    assert "status" in r.json()


def test_login_returns_jwt(client):
    c, _ = client
    r = c.post("/auth/login", data={
        "username": _ENV["ML_USER"],
        "password": _ENV["ML_USER_PASSWORD"],
    })
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["role"] == "ml_user"
    assert body["username"] == _ENV["ML_USER"]


def test_predict_returns_expected_fields(client):
    c, _ = client
    login = c.post("/auth/login", data={
        "username": _ENV["ML_USER"],
        "password": _ENV["ML_USER_PASSWORD"],
    })
    token = login.json()["access_token"]

    r = c.post("/predict",
               headers={"Authorization": f"Bearer {token}"},
               json={"model_id": "test-model", "query_text": "hello world"})

    assert r.status_code == 200
    body = r.json()
    for field in ("risk_level", "risk_score", "anomaly", "features"):
        assert field in body, f"Missing field in /predict response: {field!r}"
    assert body["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert isinstance(body["risk_score"], float)
    assert isinstance(body["anomaly"], bool)
    assert isinstance(body["features"], dict)
