"""Bearer token authentication for the tobira API."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tobira.serving.rbac import Permission, RbacConfig

_HEADER_NAME = "Authorization"
_SCHEME = "Bearer"
_ENV_VAR = "TOBIRA_API_KEY"


def get_api_key(serving_config: dict[str, Any] | None = None) -> str | None:
    """Resolve the API key from config or environment.

    Priority: environment variable ``TOBIRA_API_KEY`` > config value.

    Args:
        serving_config: Optional ``[serving]`` section from the TOML config.

    Returns:
        The API key string, or ``None`` if authentication is disabled.
    """
    env_key = os.environ.get(_ENV_VAR)
    if env_key:
        return env_key
    if serving_config:
        return serving_config.get("api_key")
    return None


def create_auth_dependency(api_key: str) -> Any:
    """Create a FastAPI dependency that enforces Bearer token auth.

    Args:
        api_key: The expected API key.

    Returns:
        A FastAPI dependency callable.
    """
    import fastapi
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

    _bearer_scheme = HTTPBearer(auto_error=False)

    async def _verify_api_key(
        credentials: HTTPAuthorizationCredentials | None = fastapi.Depends(
            _bearer_scheme
        ),
    ) -> None:
        if credentials is None or credentials.credentials != api_key:
            raise fastapi.HTTPException(
                status_code=401,
                detail="Invalid or missing API key",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return _verify_api_key


def create_rbac_auth_dependency(rbac_config: RbacConfig) -> Any:
    """Create a FastAPI dependency that authenticates via RBAC API keys.

    Resolves the Bearer token to an :class:`AuthenticatedUser` and stores
    it in ``request.state.authenticated_user`` for downstream use
    (audit logging, permission checks).

    Args:
        rbac_config: The loaded RBAC configuration.

    Returns:
        A FastAPI dependency callable.
    """
    import fastapi
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from starlette.requests import Request

    _bearer_scheme = HTTPBearer(auto_error=False)

    async def _verify_rbac(
        request,  # type: Request
        credentials: HTTPAuthorizationCredentials | None = fastapi.Depends(
            _bearer_scheme
        ),
    ) -> None:
        if credentials is None:
            raise fastapi.HTTPException(
                status_code=401,
                detail="Missing API key",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = rbac_config.resolve_user(credentials.credentials)
        if user is None:
            raise fastapi.HTTPException(
                status_code=401,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )
        request.state.authenticated_user = user  # type: ignore[attr-defined]

    # Override annotations so FastAPI resolves Request at runtime
    # (``from __future__ import annotations`` turns annotations into
    # strings that cannot reference locally-imported names).
    _verify_rbac.__annotations__["request"] = Request

    return _verify_rbac


def create_permission_dependency(required: Permission) -> Any:
    """Create a FastAPI dependency that checks a specific permission.

    Must be used *after* :func:`create_rbac_auth_dependency` in the
    dependency chain so that ``request.state.authenticated_user`` is set.

    Args:
        required: The permission to require.

    Returns:
        A FastAPI dependency callable.
    """
    import fastapi
    from starlette.requests import Request

    async def _check_permission(
        request,  # type: Request
    ) -> None:
        user = getattr(request.state, "authenticated_user", None)
        if user is None:
            raise fastapi.HTTPException(
                status_code=401,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.has_permission(required):
            raise fastapi.HTTPException(
                status_code=403,
                detail=f"Permission denied: {required.value} required",
            )

    _check_permission.__annotations__["request"] = Request

    return _check_permission
