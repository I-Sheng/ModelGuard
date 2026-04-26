"""
Security tests — mapped to Threat_Model.md.

MinIO is replaced with a MagicMock; no live services are required.
All credentials (usernames and passwords) are loaded from .env via dotenv_values.
Each test asserts that the *vulnerable* behaviour currently exists and will start
FAILING once the corresponding mitigation is applied.
"""

import io
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


def _login(c: TestClient, username: str, password: str) -> str:
    r = c.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"Login failed for {username!r}: {r.text}"
    return r.json()["access_token"]


# ---------------------------------------------------------------------------
# T-01 — Model artifact overwrite without ownership check
# ---------------------------------------------------------------------------

class TestT01ArtifactOverwrite:
    """
    POST /models/{model_id}/upload calls put_object unconditionally.
    Any authenticated customer can overwrite another user's artifact.
    """

    def test_cross_owner_upload_accepted(self, client):
        c, mock = client

        # ml_user registers and uploads the original artifact
        ml_token = _login(c, _ENV["ML_USER"], _ENV["ML_USER_PASSWORD"])
        c.post("/models/register",
               headers={"Authorization": f"Bearer {ml_token}"},
               json={"model_id": "victim-model", "name": "Legit Model", "version": "1.0"})
        c.post("/models/victim-model/upload",
               headers={"Authorization": f"Bearer {ml_token}"},
               files={"file": ("model.pkl", io.BytesIO(b"original"), "application/octet-stream")})

        # customer1 overwrites the artifact — no ownership check, so this succeeds
        customer_token = _login(c, _ENV["CUSTOMER1"], _ENV["CUSTOMER1_PASSWORD"])
        r = c.post(
            "/models/victim-model/upload",
            headers={"Authorization": f"Bearer {customer_token}"},
            files={"file": ("model.pkl", io.BytesIO(b"backdoored"), "application/octet-stream")},
        )
        assert r.status_code == 200, (
            "FIXED: cross-owner upload was rejected — ownership check is now enforced."
        )
        key = r.json()["key"]
        assert key.startswith("victim-model/"), f"Unexpected MinIO key: {key}"
        assert mock.put_object.call_count == 2, (
            "Expected two put_object calls (original + overwrite); second should have been blocked."
        )


# ---------------------------------------------------------------------------
# Invalid login — wrong credentials must never yield a token
# ---------------------------------------------------------------------------

class TestInvalidLogin:
    """
    POST /auth/login must return HTTP 401 for any unrecognised username or
    wrong password.  No access_token should be issued on failure.
    """

    @pytest.mark.parametrize("username,password", [
        ("wronguser",  "wrongpassword"),
        ("wronguser",  ""),
        ("",           "wrongpassword"),
    ])
    def test_unknown_user_rejected(self, client, username, password):
        c, _ = client
        r = c.post("/auth/login", data={"username": username, "password": password})
        assert r.status_code == 401, (
            f"Expected HTTP 401 for ({username!r}, {password!r}), got {r.status_code}"
        )
        assert "access_token" not in r.json(), (
            "No token should be issued on a failed login attempt."
        )

    def test_wrong_password_for_admin_rejected(self, client):
        c, _ = client
        r = c.post("/auth/login", data={
            "username": _ENV["ADMIN_USER"],
            "password": "wrongpassword",
        })
        assert r.status_code == 401
        assert "access_token" not in r.json()

    def test_wrong_password_for_ml_user_rejected(self, client):
        c, _ = client
        r = c.post("/auth/login", data={
            "username": _ENV["ML_USER"],
            "password": "wrongpassword",
        })
        assert r.status_code == 401
        assert "access_token" not in r.json()

    def test_wrong_password_for_customer_rejected(self, client):
        c, _ = client
        r = c.post("/auth/login", data={
            "username": _ENV["CUSTOMER1"],
            "password": "wrongpassword",
        })
        assert r.status_code == 401
        assert "access_token" not in r.json()
