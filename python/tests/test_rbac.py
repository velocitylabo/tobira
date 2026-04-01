"""Tests for tobira.serving.rbac — Role-Based Access Control."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tobira.backends.protocol import BackendProtocol, PredictionResult
from tobira.serving.rbac import (
    DEFAULT_ROLE_PERMISSIONS,
    Permission,
    Role,
    load_rbac_config,
)

_has_fastapi = True
try:
    from fastapi.testclient import TestClient
except ImportError:
    _has_fastapi = False

requires_fastapi = pytest.mark.skipif(not _has_fastapi, reason="fastapi not installed")

ADMIN_KEY = "admin-secret-key-1234567890"
OPERATOR_KEY = "operator-secret-key-1234567890"
VIEWER_KEY = "viewer-secret-key-1234567890"
API_CLIENT_KEY = "api-client-key-1234567890"


def _make_mock_backend() -> MagicMock:
    backend = MagicMock(spec=BackendProtocol)
    backend.predict.return_value = PredictionResult(
        label="spam", score=0.95, labels={"spam": 0.95, "ham": 0.05}
    )
    return backend


def _make_rbac_config() -> dict:
    return {
        "enabled": True,
        "api_keys": [
            {"key": ADMIN_KEY, "name": "admin-user", "role": "admin"},
            {"key": OPERATOR_KEY, "name": "operator-bot", "role": "operator"},
            {"key": VIEWER_KEY, "name": "dashboard", "role": "viewer"},
            {"key": API_CLIENT_KEY, "name": "mta-client", "role": "api-client"},
        ],
    }


class TestRolePermissions:
    def test_admin_has_all_permissions(self) -> None:
        perms = DEFAULT_ROLE_PERMISSIONS[Role.ADMIN]
        for p in Permission:
            assert p in perms

    def test_operator_permissions(self) -> None:
        perms = DEFAULT_ROLE_PERMISSIONS[Role.OPERATOR]
        assert Permission.PREDICT in perms
        assert Permission.VIEW_METRICS in perms
        assert Permission.MANAGE_MODELS in perms
        assert Permission.MANAGE_USERS not in perms
        assert Permission.MANAGE_TENANTS not in perms

    def test_viewer_permissions(self) -> None:
        perms = DEFAULT_ROLE_PERMISSIONS[Role.VIEWER]
        assert Permission.VIEW_METRICS in perms
        assert Permission.PREDICT not in perms

    def test_api_client_permissions(self) -> None:
        perms = DEFAULT_ROLE_PERMISSIONS[Role.API_CLIENT]
        assert Permission.PREDICT in perms
        assert len(perms) == 1


class TestLoadRbacConfig:
    def test_none_config_returns_disabled(self) -> None:
        cfg = load_rbac_config(None)
        assert not cfg.enabled
        assert cfg.api_keys == []

    def test_empty_config_returns_disabled(self) -> None:
        cfg = load_rbac_config({})
        assert not cfg.enabled

    def test_valid_config(self) -> None:
        cfg = load_rbac_config(_make_rbac_config())
        assert cfg.enabled
        assert len(cfg.api_keys) == 4
        assert cfg.api_keys[0].role == Role.ADMIN
        assert cfg.api_keys[0].name == "admin-user"

    def test_unknown_role_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown RBAC role"):
            load_rbac_config({
                "enabled": True,
                "api_keys": [{"key": "k", "name": "n", "role": "superuser"}],
            })

    def test_default_role_is_api_client(self) -> None:
        cfg = load_rbac_config({
            "enabled": True,
            "api_keys": [{"key": "k", "name": "n"}],
        })
        assert cfg.api_keys[0].role == Role.API_CLIENT


class TestRbacConfigResolveUser:
    def test_resolve_known_key(self) -> None:
        cfg = load_rbac_config(_make_rbac_config())
        user = cfg.resolve_user(ADMIN_KEY)
        assert user is not None
        assert user.key_name == "admin-user"
        assert user.role == Role.ADMIN
        assert user.has_permission(Permission.MANAGE_USERS)

    def test_resolve_unknown_key_returns_none(self) -> None:
        cfg = load_rbac_config(_make_rbac_config())
        assert cfg.resolve_user("unknown-key") is None

    def test_viewer_cannot_predict(self) -> None:
        cfg = load_rbac_config(_make_rbac_config())
        user = cfg.resolve_user(VIEWER_KEY)
        assert user is not None
        assert not user.has_permission(Permission.PREDICT)


@requires_fastapi
class TestRbacEndpoints:
    def test_predict_denied_without_token(self) -> None:
        from tobira.serving.server import create_app

        app = create_app(_make_mock_backend(), rbac=_make_rbac_config())
        client = TestClient(app)

        resp = client.post("/v1/predict", json={"text": "hello"})
        assert resp.status_code == 401

    def test_predict_denied_with_invalid_key(self) -> None:
        from tobira.serving.server import create_app

        app = create_app(_make_mock_backend(), rbac=_make_rbac_config())
        client = TestClient(app)

        resp = client.post(
            "/v1/predict",
            json={"text": "hello"},
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert resp.status_code == 401

    def test_predict_allowed_with_admin_key(self) -> None:
        from tobira.serving.server import create_app

        app = create_app(_make_mock_backend(), rbac=_make_rbac_config())
        client = TestClient(app)

        resp = client.post(
            "/v1/predict",
            json={"text": "hello"},
            headers={"Authorization": f"Bearer {ADMIN_KEY}"},
        )
        assert resp.status_code == 200

    def test_predict_allowed_with_api_client_key(self) -> None:
        from tobira.serving.server import create_app

        app = create_app(_make_mock_backend(), rbac=_make_rbac_config())
        client = TestClient(app)

        resp = client.post(
            "/v1/predict",
            json={"text": "hello"},
            headers={"Authorization": f"Bearer {API_CLIENT_KEY}"},
        )
        assert resp.status_code == 200

    def test_health_does_not_require_auth_with_rbac(self) -> None:
        from tobira.serving.server import create_app

        app = create_app(_make_mock_backend(), rbac=_make_rbac_config())
        client = TestClient(app)

        resp = client.get("/v1/health")
        assert resp.status_code == 200

    def test_rbac_disabled_allows_unauthenticated(self) -> None:
        from tobira.serving.server import create_app

        app = create_app(
            _make_mock_backend(),
            rbac={"enabled": False},
        )
        client = TestClient(app)

        resp = client.post("/v1/predict", json={"text": "hello"})
        assert resp.status_code == 200

    def test_legacy_predict_requires_rbac(self) -> None:
        from tobira.serving.server import create_app

        app = create_app(_make_mock_backend(), rbac=_make_rbac_config())
        client = TestClient(app)

        resp = client.post("/predict", json={"text": "hello"})
        assert resp.status_code == 401

    def test_rbac_overrides_simple_api_key(self) -> None:
        from tobira.serving.server import create_app

        app = create_app(
            _make_mock_backend(),
            serving={"api_key": "simple-key"},
            rbac=_make_rbac_config(),
        )
        client = TestClient(app)

        # Simple key should not work when RBAC is active
        resp = client.post(
            "/v1/predict",
            json={"text": "hello"},
            headers={"Authorization": "Bearer simple-key"},
        )
        assert resp.status_code == 401

        # RBAC key should work
        resp = client.post(
            "/v1/predict",
            json={"text": "hello"},
            headers={"Authorization": f"Bearer {ADMIN_KEY}"},
        )
        assert resp.status_code == 200
