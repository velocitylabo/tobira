"""Tests for multi-tenant support."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tobira.backends.protocol import BackendProtocol, PredictionResult
from tobira.serving.tenant import (
    TenantConfig,
    TenantRegistry,
    load_tenant_configs,
    validate_tenant_id,
)

_has_fastapi = True
try:
    from fastapi.testclient import TestClient
except ImportError:
    _has_fastapi = False

requires_fastapi = pytest.mark.skipif(not _has_fastapi, reason="fastapi not installed")


def _make_mock_backend(label: str = "spam", score: float = 0.95) -> MagicMock:
    backend = MagicMock(spec=BackendProtocol)
    backend.predict.return_value = PredictionResult(
        label=label, score=score, labels={label: score, "ham": 1.0 - score}
    )
    return backend


# ── validate_tenant_id ─────────────────────────────────────────


class TestValidateTenantId:
    def test_valid_simple(self) -> None:
        assert validate_tenant_id("org-a") is True

    def test_valid_with_underscores(self) -> None:
        assert validate_tenant_id("my_tenant_1") is True

    def test_valid_single_char(self) -> None:
        assert validate_tenant_id("a") is True

    def test_invalid_empty(self) -> None:
        assert validate_tenant_id("") is False

    def test_invalid_starts_with_hyphen(self) -> None:
        assert validate_tenant_id("-invalid") is False

    def test_invalid_special_chars(self) -> None:
        assert validate_tenant_id("org/a") is False

    def test_invalid_too_long(self) -> None:
        assert validate_tenant_id("a" * 64) is False

    def test_valid_max_length(self) -> None:
        assert validate_tenant_id("a" * 63) is True


# ── TenantRegistry ─────────────────────────────────────────────


class TestTenantRegistry:
    def test_register_and_get(self) -> None:
        from unittest.mock import patch

        registry = TenantRegistry()
        cfg = TenantConfig(
            tenant_id="org-a",
            display_name="Org A",
            backend_config={"type": "fasttext", "model_path": "/tmp/m.bin"},
        )
        with patch(
            "tobira.serving.tenant.create_backend",
            return_value=_make_mock_backend(),
        ):
            registry.register(cfg)

        assert "org-a" in registry
        assert len(registry) == 1
        assert registry.get_config("org-a") is not None
        assert registry.get_backend("org-a") is not None

    def test_register_duplicate_raises(self) -> None:
        from unittest.mock import patch

        registry = TenantRegistry()
        cfg = TenantConfig(
            tenant_id="org-a",
            backend_config={"type": "fasttext", "model_path": "/tmp/m.bin"},
        )
        with patch(
            "tobira.serving.tenant.create_backend",
            return_value=_make_mock_backend(),
        ):
            registry.register(cfg)
            with pytest.raises(ValueError, match="already registered"):
                registry.register(cfg)

    def test_register_invalid_id_raises(self) -> None:
        registry = TenantRegistry()
        cfg = TenantConfig(
            tenant_id="-bad",
            backend_config={"type": "fasttext", "model_path": "/tmp/m.bin"},
        )
        with pytest.raises(ValueError, match="Invalid tenant ID"):
            registry.register(cfg)

    def test_get_nonexistent_returns_none(self) -> None:
        registry = TenantRegistry()
        assert registry.get_backend("nonexistent") is None
        assert registry.get_config("nonexistent") is None

    def test_list_tenants_sorted(self) -> None:
        from unittest.mock import patch

        registry = TenantRegistry()
        with patch(
            "tobira.serving.tenant.create_backend",
            return_value=_make_mock_backend(),
        ):
            registry.register(
                TenantConfig(
                    tenant_id="z-tenant",
                    backend_config={"type": "fasttext", "model_path": "/tmp/m.bin"},
                )
            )
            registry.register(
                TenantConfig(
                    tenant_id="a-tenant",
                    backend_config={"type": "fasttext", "model_path": "/tmp/m.bin"},
                )
            )

        tenants = registry.list_tenants()
        assert [t.tenant_id for t in tenants] == ["a-tenant", "z-tenant"]


# ── load_tenant_configs ────────────────────────────────────────


class TestLoadTenantConfigs:
    def test_no_tenants_section(self) -> None:
        assert load_tenant_configs({}) == []

    def test_tenants_not_enabled(self) -> None:
        assert load_tenant_configs({"tenants": {"enabled": False}}) == []

    def test_load_tenants(self) -> None:
        config = {
            "tenants": {
                "enabled": True,
                "org-a": {
                    "display_name": "Org A",
                    "backend": {"type": "fasttext", "model_path": "/tmp/a.bin"},
                },
                "org-b": {
                    "backend": {"type": "onnx", "model_path": "/tmp/b.onnx"},
                },
            },
        }
        configs = load_tenant_configs(config)
        assert len(configs) == 2
        ids = {c.tenant_id for c in configs}
        assert ids == {"org-a", "org-b"}

        org_a = next(c for c in configs if c.tenant_id == "org-a")
        assert org_a.display_name == "Org A"
        assert org_a.backend_config["type"] == "fasttext"

        org_b = next(c for c in configs if c.tenant_id == "org-b")
        assert org_b.display_name == "org-b"  # defaults to key


# ── API integration tests ──────────────────────────────────────


@requires_fastapi
class TestTenantApi:
    def _make_registry(self) -> TenantRegistry:
        from unittest.mock import patch

        registry = TenantRegistry()
        with patch(
            "tobira.serving.tenant.create_backend",
        ) as mock_create:
            mock_create.return_value = _make_mock_backend("spam", 0.9)
            registry.register(
                TenantConfig(
                    tenant_id="org-a",
                    display_name="Org A",
                    backend_config={"type": "fasttext", "model_path": "/a.bin"},
                )
            )
            mock_create.return_value = _make_mock_backend("ham", 0.8)
            registry.register(
                TenantConfig(
                    tenant_id="org-b",
                    display_name="Org B",
                    backend_config={"type": "fasttext", "model_path": "/b.bin"},
                )
            )
        return registry

    def test_predict_with_tenant_header(self) -> None:
        from tobira.serving.server import create_app

        registry = self._make_registry()
        app = create_app(
            _make_mock_backend(),
            tenant_registry=registry,
        )
        client = TestClient(app)

        resp = client.post(
            "/v1/predict",
            json={"text": "hello"},
            headers={"X-Tobira-Tenant": "org-a"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["label"] == "spam"
        assert data["tenant"] == "org-a"

    def test_predict_with_different_tenant(self) -> None:
        from tobira.serving.server import create_app

        registry = self._make_registry()
        app = create_app(
            _make_mock_backend(),
            tenant_registry=registry,
        )
        client = TestClient(app)

        resp = client.post(
            "/v1/predict",
            json={"text": "hello"},
            headers={"X-Tobira-Tenant": "org-b"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["label"] == "ham"
        assert data["tenant"] == "org-b"

    def test_predict_missing_tenant_header_returns_400(self) -> None:
        from tobira.serving.server import create_app

        registry = self._make_registry()
        app = create_app(
            _make_mock_backend(),
            tenant_registry=registry,
        )
        client = TestClient(app)

        resp = client.post("/v1/predict", json={"text": "hello"})
        assert resp.status_code == 400

    def test_predict_unknown_tenant_returns_404(self) -> None:
        from tobira.serving.server import create_app

        registry = self._make_registry()
        app = create_app(
            _make_mock_backend(),
            tenant_registry=registry,
        )
        client = TestClient(app)

        resp = client.post(
            "/v1/predict",
            json={"text": "hello"},
            headers={"X-Tobira-Tenant": "unknown"},
        )
        assert resp.status_code == 404

    def test_tenant_list_endpoint(self) -> None:
        from tobira.serving.server import create_app

        registry = self._make_registry()
        app = create_app(
            _make_mock_backend(),
            tenant_registry=registry,
        )
        client = TestClient(app)

        resp = client.get("/v1/tenants")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        ids = {t["tenant_id"] for t in data["tenants"]}
        assert ids == {"org-a", "org-b"}

    def test_no_tenant_list_without_registry(self) -> None:
        from tobira.serving.server import create_app

        app = create_app(_make_mock_backend())
        client = TestClient(app)

        resp = client.get("/v1/tenants")
        assert resp.status_code == 404

    def test_predict_without_multitenancy_no_tenant_field(self) -> None:
        from tobira.serving.server import create_app

        app = create_app(_make_mock_backend())
        client = TestClient(app)

        resp = client.post("/v1/predict", json={"text": "hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant"] is None

    def test_health_does_not_require_tenant_header(self) -> None:
        from tobira.serving.server import create_app

        registry = self._make_registry()
        app = create_app(
            _make_mock_backend(),
            tenant_registry=registry,
        )
        client = TestClient(app)

        resp = client.get("/v1/health")
        assert resp.status_code == 200

    def test_tenant_data_isolation_feedback(self, tmp_path: Path) -> None:
        """Feedback from different tenants goes to different files."""
        from tobira.serving.server import create_app

        registry = self._make_registry()
        feedback_path = str(tmp_path / "feedback.jsonl")
        app = create_app(
            _make_mock_backend(),
            feedback={"enabled": True, "store_path": feedback_path},
            tenant_registry=registry,
        )
        client = TestClient(app)

        # Tenant A feedback
        resp = client.post(
            "/v1/feedback",
            json={"text": "spam message", "label": "spam", "source": "test"},
            headers={"X-Tobira-Tenant": "org-a"},
        )
        assert resp.status_code == 200

        # Tenant B feedback
        resp = client.post(
            "/v1/feedback",
            json={"text": "ham message", "label": "ham", "source": "test"},
            headers={"X-Tobira-Tenant": "org-b"},
        )
        assert resp.status_code == 200

        # Check files are separate
        a_path = tmp_path / "feedback_org-a.jsonl"
        b_path = tmp_path / "feedback_org-b.jsonl"
        assert a_path.exists()
        assert b_path.exists()


# ── CLI tests ──────────────────────────────────────────────────


class TestTenantCli:
    def test_tenant_list_no_tenants(self, tmp_path: Path) -> None:
        from tobira.cli.tenant import _cmd_tenant_list

        config_file = tmp_path / "tobira.toml"
        config_file.write_text('[backend]\ntype = "fasttext"\nmodel_path = "/tmp/m"\n')

        args = MagicMock()
        args.config = str(config_file)
        assert _cmd_tenant_list(args) == 0

    def test_tenant_list_with_tenants(self, tmp_path: Path) -> None:
        from tobira.cli.tenant import _cmd_tenant_list

        config_file = tmp_path / "tobira.toml"
        config_file.write_text(
            '[backend]\ntype = "fasttext"\nmodel_path = "/tmp/m"\n'
            "\n[tenants]\nenabled = true\n"
            '\n[tenants.org-a]\ndisplay_name = "Org A"\n'
            '\n[tenants.org-a.backend]\ntype = "fasttext"\nmodel_path = "/tmp/a"\n'
        )

        args = MagicMock()
        args.config = str(config_file)
        assert _cmd_tenant_list(args) == 0

    def test_tenant_create(self, tmp_path: Path) -> None:
        from tobira.cli.tenant import _cmd_tenant_create

        config_file = tmp_path / "tobira.toml"
        config_file.write_text('[backend]\ntype = "fasttext"\nmodel_path = "/tmp/m"\n')

        args = MagicMock()
        args.config = str(config_file)
        args.name = "new-tenant"
        args.display_name = "New Tenant"
        args.backend_type = "fasttext"
        args.model_path = "/tmp/new.bin"
        assert _cmd_tenant_create(args) == 0

        # Verify the file was updated
        from tobira.config import load_toml

        config = load_toml(str(config_file))
        assert "tenants" in config
        assert config["tenants"]["enabled"] is True
        assert "new-tenant" in config["tenants"]

    def test_tenant_create_invalid_id(self, tmp_path: Path) -> None:
        from tobira.cli.tenant import _cmd_tenant_create

        config_file = tmp_path / "tobira.toml"
        config_file.write_text('[backend]\ntype = "fasttext"\nmodel_path = "/tmp/m"\n')

        args = MagicMock()
        args.config = str(config_file)
        args.name = "-invalid"
        args.display_name = ""
        args.backend_type = "fasttext"
        args.model_path = ""
        assert _cmd_tenant_create(args) == 1

    def test_tenant_delete(self, tmp_path: Path) -> None:
        from tobira.cli.tenant import _cmd_tenant_delete

        config_file = tmp_path / "tobira.toml"
        config_file.write_text(
            '[backend]\ntype = "fasttext"\nmodel_path = "/tmp/m"\n'
            "\n[tenants]\nenabled = true\n"
            '\n[tenants.old-tenant]\ndisplay_name = "Old"\n'
            '\n[tenants.old-tenant.backend]\ntype = "fasttext"\n'
            'model_path = "/tmp/old"\n'
            "\n[serving]\n"
        )

        args = MagicMock()
        args.config = str(config_file)
        args.name = "old-tenant"
        assert _cmd_tenant_delete(args) == 0

        # Verify the tenant was removed
        from tobira.config import load_toml

        config = load_toml(str(config_file))
        tenants = config.get("tenants", {})
        assert "old-tenant" not in tenants
        # Other sections preserved
        assert "serving" in config

    def test_tenant_delete_nonexistent(self, tmp_path: Path) -> None:
        from tobira.cli.tenant import _cmd_tenant_delete

        config_file = tmp_path / "tobira.toml"
        config_file.write_text('[backend]\ntype = "fasttext"\nmodel_path = "/tmp/m"\n')

        args = MagicMock()
        args.config = str(config_file)
        args.name = "nonexistent"
        assert _cmd_tenant_delete(args) == 1
