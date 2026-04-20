"""
Security tests for ModelGuard AI — one test class per threat in Threat_Model.md.

MinIO is replaced with a MagicMock; no live services are required.

Each test asserts that the *vulnerable* behaviour currently exists.
Tests will start FAILING once the corresponding mitigation is applied — that is
the intended outcome.  The assertion message on failure tells you what was fixed.
"""

import io
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

# Ensure the api directory is on sys.path when running from the repo root
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import app, JWT_SECRET, JWT_ALGORITHM, _USERS  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------

def _make_minio_mock() -> MagicMock:
    m = MagicMock()
    m.bucket_exists.return_value = True
    m.list_buckets.return_value = []
    m.list_objects.return_value = iter([])
    m.put_object.return_value = None
    m.get_object.return_value = MagicMock(
        read=MagicMock(return_value=b'{"model_id": "test", "name": "Test Model"}')
    )
    m.remove_object.return_value = None
    return m


@pytest.fixture()
def minio_mock():
    return _make_minio_mock()


@pytest.fixture()
def client(minio_mock):
    """TestClient with MinIO and startup bucket-init patched out."""
    with patch("main.get_minio", return_value=minio_mock), \
         patch("main.ensure_buckets"):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c, minio_mock


@pytest.fixture(autouse=True)
def _reset_rate_window():
    """Prevent cross-test pollution in the global query-rate window."""
    import main
    main._query_window.clear()
    yield
    main._query_window.clear()


def _forge_token(username: str = "admin", role: str = "admin",
                 secret: str = JWT_SECRET) -> str:
    """Sign a JWT with a known secret — no credentials required."""
    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    return jwt.encode(
        {"sub": username, "role": role, "exp": expire},
        secret,
        algorithm=JWT_ALGORITHM,
    )


def _login(c: TestClient, username: str, password: str) -> str:
    r = c.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


COMPOSE_PATH = os.path.join(os.path.dirname(__file__), "..", "docker-compose.yml")


# ---------------------------------------------------------------------------
# T-01 — JWT signing secret committed to public repository
# ---------------------------------------------------------------------------

class TestT01JwtSecretExposed:
    """
    JWT_SECRET_KEY defaults to a well-known string committed in main.py.
    Any source-code reader can forge admin tokens without credentials.
    """

    def test_default_secret_matches_known_value(self):
        assert JWT_SECRET == "modelguard-dev-secret-change-in-production", (
            "FIXED: JWT_SECRET_KEY is no longer the hardcoded default. "
            "Confirm it is injected from the environment."
        )

    def test_forged_token_accepted_on_protected_endpoint(self, client):
        c, _ = client
        token = _forge_token(username="attacker", role="admin")
        r = c.get("/health/detail", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, (
            "FIXED: forged token was rejected — JWT_SECRET_KEY is no longer public."
        )

    def test_forged_token_grants_claimed_role(self, client):
        c, _ = client
        token = _forge_token(username="nobody", role="admin")
        r = c.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["username"] == "nobody"
        assert data["role"] == "admin"


# ---------------------------------------------------------------------------
# T-02 — Hardcoded user credentials in source code
# ---------------------------------------------------------------------------

class TestT02HardcodedCredentials:
    """
    _USERS in main.py contains plaintext passwords committed to the repository.
    Any reader of the source can authenticate as any role without brute-forcing.
    """

    def test_plaintext_password_importable_from_source(self):
        assert "admin" in _USERS, "admin user must exist"
        assert "password" in _USERS["admin"], (
            "FIXED: plaintext password key removed from _USERS."
        )
        assert _USERS["admin"]["password"] == "admin_password", (
            "FIXED: admin password is no longer the hardcoded default."
        )

    def test_source_password_authenticates_admin(self, client):
        c, _ = client
        r = c.post("/auth/login",
                   data={"username": "admin", "password": "admin_password"})
        assert r.status_code == 200
        assert r.json()["role"] == "admin", (
            "FIXED: hardcoded admin_password no longer works."
        )

    def test_source_password_authenticates_customer(self, client):
        c, _ = client
        r = c.post("/auth/login",
                   data={"username": "customer1", "password": "customer_password"})
        assert r.status_code == 200
        assert r.json()["role"] == "customer", (
            "FIXED: hardcoded customer_password no longer works."
        )

    def test_source_password_authenticates_ml_user(self, client):
        c, _ = client
        r = c.post("/auth/login",
                   data={"username": "ml_user", "password": "ml_password"})
        assert r.status_code == 200
        assert r.json()["role"] == "ml_user", (
            "FIXED: hardcoded ml_password no longer works."
        )


# ---------------------------------------------------------------------------
# T-03 — Default MinIO credentials hardcoded in docker-compose.yml
# ---------------------------------------------------------------------------

class TestT03MinioDefaultCredentials:
    """
    docker-compose.yml hardcodes minioadmin/minioadmin for both MinIO and
    the backend environment.  Any host that can reach port 9000 has full
    bucket access with these credentials.
    """

    def _compose_text(self) -> str:
        with open(COMPOSE_PATH) as f:
            return f.read()

    def test_minio_root_user_is_default(self):
        assert "MINIO_ROOT_USER: minioadmin" in self._compose_text(), (
            "FIXED: MINIO_ROOT_USER is no longer the default 'minioadmin'."
        )

    def test_minio_root_password_is_default(self):
        assert "MINIO_ROOT_PASSWORD: minioadmin" in self._compose_text(), (
            "FIXED: MINIO_ROOT_PASSWORD is no longer the default 'minioadmin'."
        )

    def test_backend_env_uses_default_access_key(self):
        assert "MINIO_ACCESS_KEY: minioadmin" in self._compose_text(), (
            "FIXED: backend MINIO_ACCESS_KEY is no longer the default 'minioadmin'."
        )

    def test_backend_env_uses_default_secret_key(self):
        assert "MINIO_SECRET_KEY: minioadmin" in self._compose_text(), (
            "FIXED: backend MINIO_SECRET_KEY is no longer the default 'minioadmin'."
        )


# ---------------------------------------------------------------------------
# T-04 — Unauthenticated POST /models/register
# ---------------------------------------------------------------------------

class TestT04UnauthenticatedModelRegistration:
    """
    POST /models/register has no auth dependency — any caller can register or
    overwrite any model's metadata without a valid token.
    """

    def test_register_succeeds_without_auth(self, client):
        c, _ = client
        r = c.post("/models/register", json={
            "model_id": "rogue-model",
            "name": "Rogue",
            "version": "1.0",
        })
        assert r.status_code == 200, (
            f"FIXED: unauthenticated registration was rejected (HTTP {r.status_code}). "
            "Ensure POST /models/register requires authentication."
        )

    def test_unauthenticated_overwrite_is_accepted(self, client):
        c, mock = client
        for name in ("Original", "Poisoned"):
            c.post("/models/register", json={
                "model_id": "victim-model",
                "name": name,
                "version": "1.0",
            })
        # Two separate put_object calls means the overwrite was never blocked
        assert mock.put_object.call_count >= 2, (
            "FIXED: the second unauthenticated registration was blocked."
        )

    def test_authenticated_register_still_works(self, client):
        """Baseline: an admin can always register a model."""
        c, _ = client
        token = _forge_token(role="admin")
        r = c.post("/models/register",
                   headers={"Authorization": f"Bearer {token}"},
                   json={"model_id": "legit-model", "name": "Legit", "version": "1.0"})
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# T-05 — Path traversal via unsanitized filename in artifact upload
# ---------------------------------------------------------------------------

class TestT05PathTraversalArtifactUpload:
    """
    POST /models/{model_id}/upload uses file.filename directly in the MinIO key.
    A crafted filename containing '../' can overwrite arbitrary objects in the
    same bucket prefix.
    """

    def _customer_token(self, c: TestClient) -> str:
        return _login(c, "customer1", "customer_password")

    def test_traversal_filename_reaches_minio(self, client):
        c, mock = client
        token = self._customer_token(c)
        r = c.post(
            "/models/target-model/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("../metadata.json", io.BytesIO(b"evil"), "application/json")},
        )
        assert r.status_code == 200, (
            "FIXED: upload with traversal filename was rejected."
        )
        key_arg = mock.put_object.call_args[0][1]
        assert ".." in key_arg, (
            f"FIXED: filename was sanitized before storage. Actual key: {key_arg}"
        )

    def test_traversal_key_resolves_to_metadata_path(self, client):
        """Show that the traversal key normalises to the model's metadata.json."""
        c, mock = client
        token = self._customer_token(c)
        c.post(
            "/models/target-model/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("../metadata.json", io.BytesIO(b"x"), "application/json")},
        )
        key_arg = mock.put_object.call_args[0][1]
        normalized = os.path.normpath(key_arg)
        expected = os.path.normpath("target-model/metadata.json")
        assert normalized == expected, (
            f"Key '{key_arg}' normalises to '{normalized}', expected '{expected}'."
        )


# ---------------------------------------------------------------------------
# T-06 — Feature evasion via public training distribution
# ---------------------------------------------------------------------------

class TestT06FeatureEvasion:
    """
    The Isolation Forest's training distribution is hardcoded and public.
    Queries shaped to match the normal region receive LOW/MEDIUM risk scores
    regardless of their actual extraction intent.
    """

    def _ml_token(self, c: TestClient) -> str:
        return _login(c, "ml_user", "ml_password")

    @staticmethod
    def _craft_normal_query(target_length: int = 120) -> str:
        """
        Produce a query whose features match the published training distribution:
          query_length ~ N(120, 40), unique_token_ratio ~ N(0.6, 0.1),
          entropy ~ N(3.5, 0.5), request_rate_1m ~ 1.
        """
        import random
        vocab = ["the", "quick", "brown", "fox", "jumps", "over", "lazy",
                 "dog", "and", "a", "in", "to", "of", "is", "it", "on"]
        random.seed(1)
        tokens = []
        while len(" ".join(tokens)) < target_length:
            tokens.append(random.choice(vocab))
        return " ".join(tokens)[:target_length]

    def test_training_parameters_are_public(self):
        """The exact training distribution parameters are importable from main."""
        import main
        assert main._TRAIN_DATA is not None
        assert main._TRAIN_DATA.shape == (500, 4), (
            "Training data shape changed — update evasion query parameters."
        )

    def test_shaped_query_scores_low_or_medium(self, client):
        c, _ = client
        token = self._ml_token(c)
        r = c.post("/predict",
                   headers={"Authorization": f"Bearer {token}"},
                   json={"model_id": "test", "query_text": self._craft_normal_query(120)})
        assert r.status_code == 200
        body = r.json()
        assert body["risk_level"] in ("LOW", "MEDIUM"), (
            f"Query scored {body['risk_level']} ({body['risk_score']:.1f}) — "
            "evasion harder than expected; consider updating the shaped query."
        )

    def test_single_slow_query_rate_feature_is_one(self, client):
        """A single request produces rate=1, well within the normal range of ~2."""
        c, _ = client
        import main
        main._query_window.clear()
        token = self._ml_token(c)
        r = c.post("/predict",
                   headers={"Authorization": f"Bearer {token}"},
                   json={"model_id": "test", "query_text": self._craft_normal_query()})
        assert r.json()["features"]["request_rate_1m"] == 1

    def test_rate_window_is_not_per_client(self, client):
        """
        _query_window is process-global — multiple client_ids share the same
        rate counter, so per-client extraction speed cannot be tracked.
        """
        c, _ = client
        token = self._ml_token(c)
        import main
        main._query_window.clear()
        for cid in ("client-A", "client-B", "client-C"):
            c.post("/predict",
                   headers={"Authorization": f"Bearer {token}"},
                   json={"model_id": "test", "query_text": "hello world", "client_id": cid})
        # All three queries share the same window; each sees the accumulated rate
        assert len(main._query_window) == 3, (
            "FIXED: per-client rate tracking is now in place."
        )


# ---------------------------------------------------------------------------
# T-07 — Audit log deletion with no MinIO object lock
# ---------------------------------------------------------------------------

class TestT07NoAuditLogObjectLock:
    """
    The minio-init container never enables object locking (WORM) on the audit
    buckets.  An attacker with MinIO credentials can delete all evidence.
    """

    def _compose_text(self) -> str:
        with open(COMPOSE_PATH) as f:
            return f.read()

    def test_minio_init_does_not_configure_object_lock(self):
        text = self._compose_text()
        assert "object-lock" not in text, (
            "FIXED: minio-init now configures object locking on audit buckets."
        )

    def test_minio_init_does_not_set_retention_policy(self):
        text = self._compose_text()
        assert "retention" not in text, (
            "FIXED: minio-init now sets a retention policy."
        )

    def test_remove_object_succeeds_with_no_lock(self, client):
        """MinIO delete is never blocked; remove_object completes without error."""
        _, mock = client
        import main
        mc = main.get_minio()
        try:
            mc.remove_object("modelguard-auditlog", "test/2026-04-20/fake.json")
        except Exception as exc:
            pytest.fail(f"remove_object raised unexpectedly: {exc}")
        mock.remove_object.assert_called_once()


# ---------------------------------------------------------------------------
# T-08 — No rate limiting or query size cap (storage exhaustion DoS)
# ---------------------------------------------------------------------------

class TestT08NoCapsOrRateLimit:
    """
    No rate-limiting middleware exists and query_text has no max_length validator.
    An attacker can flood the API with large payloads to exhaust MinIO storage.
    """

    def _ml_token(self, c: TestClient) -> str:
        return _login(c, "ml_user", "ml_password")

    def test_query_text_has_no_max_length_constraint(self):
        import main
        field = main.QueryRequest.model_fields["query_text"]
        has_max = any(
            hasattr(m, "max_length") and m.max_length is not None
            for m in field.metadata
        )
        assert not has_max, (
            "FIXED: query_text now has a max_length constraint."
        )

    def test_100kb_query_text_is_accepted(self, client):
        c, _ = client
        token = self._ml_token(c)
        r = c.post("/predict",
                   headers={"Authorization": f"Bearer {token}"},
                   json={"model_id": "test", "query_text": "A" * 100_000})
        assert r.status_code == 200, (
            f"FIXED: oversized query_text was rejected with HTTP {r.status_code}."
        )

    def test_no_rate_limit_middleware_installed(self):
        rate_limit_classes = {"SlowAPIMiddleware", "RateLimitMiddleware", "ThrottleMiddleware"}
        installed = {m.cls.__name__ for m in app.user_middleware}
        overlap = rate_limit_classes & installed
        assert not overlap, (
            f"FIXED: rate-limiting middleware is now installed: {overlap}"
        )

    def test_minio_write_failure_silently_returns_200(self, client, minio_mock):
        c, _ = client
        minio_mock.put_object.side_effect = Exception("disk full")
        token = self._ml_token(c)
        r = c.post("/predict",
                   headers={"Authorization": f"Bearer {token}"},
                   json={"model_id": "test", "query_text": "normal text"})
        assert r.status_code == 200, (
            "API should not surface MinIO errors to the caller."
        )
        assert r.json()["audit_log_key"] == "minio-unavailable", (
            "FIXED: MinIO write failure is no longer silently ignored."
        )
