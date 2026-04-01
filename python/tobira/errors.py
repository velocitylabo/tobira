"""Shared error types and error code registry for tobira.

Error Code Scheme
-----------------
Codes follow a module-level prefix scheme::

    BACKEND_*   – backend loading / inference errors
    CONFIG_*    – configuration file errors
    SERVING_*   – API server errors
    CLI_*       – CLI-specific errors
    DATA_*      – dataset / data-loading errors

Each code is a short, stable string (not a number) so that consumers can
match on it without worrying about renumbering.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Error codes (module-level constants)
# ---------------------------------------------------------------------------

# Backend errors
BACKEND_UNKNOWN_TYPE = "BACKEND_UNKNOWN_TYPE"
BACKEND_INIT_FAILED = "BACKEND_INIT_FAILED"
BACKEND_IMPORT_ERROR = "BACKEND_IMPORT_ERROR"
BACKEND_MODEL_NOT_FOUND = "BACKEND_MODEL_NOT_FOUND"
BACKEND_INFERENCE_FAILED = "BACKEND_INFERENCE_FAILED"
BACKEND_VALIDATION_ERROR = "BACKEND_VALIDATION_ERROR"

# Config errors
CONFIG_NOT_FOUND = "CONFIG_NOT_FOUND"
CONFIG_INVALID_SYNTAX = "CONFIG_INVALID_SYNTAX"
CONFIG_MISSING_SECTION = "CONFIG_MISSING_SECTION"

# Serving errors
SERVING_NOT_READY = "SERVING_NOT_READY"
SERVING_IMPORT_ERROR = "SERVING_IMPORT_ERROR"
SERVING_NOT_FOUND = "SERVING_NOT_FOUND"
SERVING_VALIDATION_ERROR = "SERVING_VALIDATION_ERROR"

# Auth / RBAC errors
AUTH_MISSING_KEY = "AUTH_MISSING_KEY"
AUTH_INVALID_KEY = "AUTH_INVALID_KEY"
AUTH_PERMISSION_DENIED = "AUTH_PERMISSION_DENIED"

# Data errors
DATA_NOT_FOUND = "DATA_NOT_FOUND"
DATA_INVALID_FORMAT = "DATA_INVALID_FORMAT"
DATA_EMPTY = "DATA_EMPTY"
DATA_MISSING_COLUMNS = "DATA_MISSING_COLUMNS"

# Tenant errors
TENANT_INVALID_ID = "TENANT_INVALID_ID"
TENANT_NOT_FOUND = "TENANT_NOT_FOUND"
TENANT_ALREADY_EXISTS = "TENANT_ALREADY_EXISTS"
TENANT_HEADER_MISSING = "TENANT_HEADER_MISSING"

# CLI errors
CLI_INVALID_ARGUMENT = "CLI_INVALID_ARGUMENT"


# ---------------------------------------------------------------------------
# Base exception
# ---------------------------------------------------------------------------


class TobiraError(Exception):
    """Base exception for all tobira errors.

    Attributes:
        code: A stable error code string (e.g. ``"BACKEND_UNKNOWN_TYPE"``).
        detail: Human-readable description of the problem.
        hint: Optional remediation suggestion.
    """

    def __init__(
        self,
        code: str,
        detail: str,
        hint: str | None = None,
    ) -> None:
        self.code = code
        self.detail = detail
        self.hint = hint
        parts = [detail]
        if hint:
            parts.append(f"Hint: {hint}")
        super().__init__(" ".join(parts))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def format_cli_error(code: str, detail: str, hint: str | None = None) -> str:
    """Format an error message for CLI output.

    Returns a string like::

        Error [BACKEND_UNKNOWN_TYPE]: Unknown backend type: 'foo'
        Hint: Available types: fasttext, bert, onnx, ...

    Args:
        code: Error code string.
        detail: Human-readable detail message.
        hint: Optional remediation hint.

    Returns:
        Formatted error string.
    """
    msg = f"Error [{code}]: {detail}"
    if hint:
        msg += f"\nHint: {hint}"
    return msg
