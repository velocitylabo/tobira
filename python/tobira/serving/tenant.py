"""Multi-tenant management for tobira.

Provides tenant configuration, registration, and request-scoped
tenant resolution via the ``X-Tobira-Tenant`` header.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from tobira.backends.factory import create_backend
from tobira.backends.protocol import BackendProtocol

logger = logging.getLogger(__name__)

_TENANT_HEADER = "X-Tobira-Tenant"
_TENANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$")


@dataclass(frozen=True)
class TenantConfig:
    """Configuration for a single tenant.

    Attributes:
        tenant_id: Unique identifier for the tenant (alphanumeric, hyphens,
            underscores; max 63 chars).
        display_name: Human-readable name for the tenant.
        backend_config: Backend configuration dict passed to
            :func:`~tobira.backends.factory.create_backend`.
    """

    tenant_id: str
    display_name: str = ""
    backend_config: dict[str, Any] = field(default_factory=dict)


def validate_tenant_id(tenant_id: str) -> bool:
    """Check whether *tenant_id* is a valid identifier.

    Valid IDs start with an alphanumeric character and may contain
    alphanumerics, hyphens, and underscores (1-63 chars).
    """
    return bool(_TENANT_ID_PATTERN.match(tenant_id))


class TenantRegistry:
    """In-memory registry of tenants and their backends.

    Backends are created eagerly during :meth:`register` so that
    model-loading errors surface at startup rather than at request time.
    """

    def __init__(self) -> None:
        self._tenants: dict[str, TenantConfig] = {}
        self._backends: dict[str, BackendProtocol] = {}

    def register(self, config: TenantConfig) -> None:
        """Register a tenant and create its backend.

        Raises:
            ValueError: If the tenant ID is invalid or already registered.
        """
        if not validate_tenant_id(config.tenant_id):
            raise ValueError(
                f"Invalid tenant ID: {config.tenant_id!r}. "
                "Must match [a-zA-Z0-9][a-zA-Z0-9_-]{0,62}."
            )
        if config.tenant_id in self._tenants:
            raise ValueError(
                f"Tenant {config.tenant_id!r} is already registered."
            )
        backend = create_backend(config.backend_config)
        self._tenants[config.tenant_id] = config
        self._backends[config.tenant_id] = backend
        logger.info("Registered tenant %r", config.tenant_id)

    def get_backend(self, tenant_id: str) -> BackendProtocol | None:
        """Return the backend for *tenant_id*, or ``None``."""
        return self._backends.get(tenant_id)

    def get_config(self, tenant_id: str) -> TenantConfig | None:
        """Return the config for *tenant_id*, or ``None``."""
        return self._tenants.get(tenant_id)

    def list_tenants(self) -> list[TenantConfig]:
        """Return all registered tenants sorted by ID."""
        return sorted(self._tenants.values(), key=lambda t: t.tenant_id)

    def __contains__(self, tenant_id: str) -> bool:
        return tenant_id in self._tenants

    def __len__(self) -> int:
        return len(self._tenants)


def load_tenant_configs(config: dict[str, Any]) -> list[TenantConfig]:
    """Parse the ``[tenants]`` section from a TOML config dict.

    Expected structure::

        [tenants]
        enabled = true

        [tenants.org-a]
        display_name = "Organization A"
        backend.type = "fasttext"
        backend.model_path = "/models/org-a/model.bin"

    Args:
        config: The full parsed TOML configuration dict.

    Returns:
        A list of :class:`TenantConfig` instances. Returns an empty list
        when the ``[tenants]`` section is absent or ``enabled`` is false.
    """
    tenants_section = config.get("tenants")
    if not tenants_section or not tenants_section.get("enabled"):
        return []

    configs: list[TenantConfig] = []
    for key, value in tenants_section.items():
        if key == "enabled" or not isinstance(value, dict):
            continue
        backend_config = value.get("backend", {})
        display_name = value.get("display_name", key)
        configs.append(
            TenantConfig(
                tenant_id=key,
                display_name=display_name,
                backend_config=backend_config,
            )
        )
    return configs


def create_tenant_dependency(registry: TenantRegistry) -> Any:
    """Create a FastAPI dependency that resolves the tenant from the request.

    The tenant is identified by the ``X-Tobira-Tenant`` header. When the
    header is missing, a 400 error is returned. When the tenant is unknown,
    a 404 error is returned.

    Returns:
        A FastAPI dependency callable that yields the tenant ID string.
    """
    import fastapi

    async def _resolve_tenant(
        x_tobira_tenant: str = fastapi.Header(default=None),
    ) -> str:
        if not x_tobira_tenant:
            raise fastapi.HTTPException(
                status_code=400,
                detail=f"Missing {_TENANT_HEADER} header",
            )
        if x_tobira_tenant not in registry:
            raise fastapi.HTTPException(
                status_code=404,
                detail=f"Unknown tenant: {x_tobira_tenant!r}",
            )
        return x_tobira_tenant

    return _resolve_tenant
