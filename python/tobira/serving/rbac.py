"""Role-Based Access Control (RBAC) for the tobira API.

Defines roles, permissions, and role-permission mappings. Roles and
API key bindings are configured in ``tobira.toml`` under the ``[rbac]``
section.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class Permission(enum.Enum):
    """Granular permissions for API operations."""

    PREDICT = "predict"
    MANAGE_MODELS = "manage_models"
    MANAGE_TENANTS = "manage_tenants"
    VIEW_METRICS = "view_metrics"
    MANAGE_USERS = "manage_users"


class Role(enum.Enum):
    """Built-in roles with pre-defined permission sets."""

    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"
    API_CLIENT = "api-client"


#: Default permission mapping for each built-in role.
DEFAULT_ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.OPERATOR: frozenset({
        Permission.PREDICT,
        Permission.MANAGE_MODELS,
        Permission.VIEW_METRICS,
    }),
    Role.VIEWER: frozenset({
        Permission.VIEW_METRICS,
    }),
    Role.API_CLIENT: frozenset({
        Permission.PREDICT,
    }),
}


@dataclass(frozen=True)
class ApiKeyEntry:
    """An API key with associated identity and role.

    Attributes:
        key: The raw API key string.
        name: Human-readable name for this key (e.g. ``"ci-bot"``).
        role: The role assigned to this key.
    """

    key: str
    name: str
    role: Role


@dataclass(frozen=True)
class AuthenticatedUser:
    """Represents an authenticated API caller.

    Attributes:
        key_name: The name of the API key used.
        role: The role associated with the key.
        permissions: Resolved permission set for the role.
    """

    key_name: str
    role: Role
    permissions: frozenset[Permission]

    def has_permission(self, perm: Permission) -> bool:
        """Check whether this user has *perm*."""
        return perm in self.permissions


@dataclass
class RbacConfig:
    """RBAC configuration loaded from ``[rbac]`` in ``tobira.toml``.

    Attributes:
        enabled: Whether RBAC is active.
        api_keys: Registered API keys with roles.
        role_permissions: Permission mapping (defaults are used when omitted).
    """

    enabled: bool = False
    api_keys: list[ApiKeyEntry] = field(default_factory=list)
    role_permissions: dict[Role, frozenset[Permission]] = field(
        default_factory=lambda: dict(DEFAULT_ROLE_PERMISSIONS),
    )

    def resolve_user(self, raw_key: str) -> AuthenticatedUser | None:
        """Look up an API key and return the authenticated user.

        Returns ``None`` if the key is not found.
        """
        for entry in self.api_keys:
            if entry.key == raw_key:
                perms = self.role_permissions.get(
                    entry.role, DEFAULT_ROLE_PERMISSIONS.get(entry.role, frozenset()),
                )
                return AuthenticatedUser(
                    key_name=entry.name,
                    role=entry.role,
                    permissions=perms,
                )
        return None


def load_rbac_config(config: dict[str, Any] | None) -> RbacConfig:
    """Build an :class:`RbacConfig` from the ``[rbac]`` TOML section.

    Expected TOML structure::

        [rbac]
        enabled = true

        [[rbac.api_keys]]
        key = "secret-key-1"
        name = "ci-bot"
        role = "operator"

        [[rbac.api_keys]]
        key = "secret-key-2"
        name = "dashboard"
        role = "viewer"

    Args:
        config: The ``[rbac]`` dict from the TOML config, or ``None``.

    Returns:
        A populated :class:`RbacConfig`.
    """
    if not config:
        return RbacConfig()

    enabled = bool(config.get("enabled", False))
    api_keys: list[ApiKeyEntry] = []
    for entry in config.get("api_keys", []):
        role_str = entry.get("role", "api-client")
        try:
            role = Role(role_str)
        except ValueError:
            raise ValueError(
                f"Unknown RBAC role: {role_str!r}. "
                f"Valid roles: {[r.value for r in Role]}"
            )
        api_keys.append(ApiKeyEntry(
            key=entry["key"],
            name=entry.get("name", "unnamed"),
            role=role,
        ))

    return RbacConfig(enabled=enabled, api_keys=api_keys)
