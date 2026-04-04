"""
Centralized authentication mode configuration.

Reads AUTH_MODE from the environment and provides helpers for
role-based access checks used across routers and middleware.

IMPORTANT: In ``none`` and ``password`` modes, all RBAC guards
(admin_guard, require_admin, etc.) are intentionally no-ops.
This means every user has full access in those modes -- they
exist only for simple / dev installations.  Set AUTH_MODE=local
or AUTH_MODE=ldap to enable real role-based access control.
"""

import os
from typing import Literal, Optional

from fastapi import Request

from open_notebook.exceptions import ForbiddenError, InvalidInputError

AuthMode = Literal["none", "password", "local", "ldap"]

_VALID_MODES: set[str] = {"none", "password", "local", "ldap"}


def get_auth_mode() -> AuthMode:
    mode = os.environ.get("AUTH_MODE", "none").strip().lower()
    if mode not in _VALID_MODES:
        raise InvalidInputError(
            f"Invalid AUTH_MODE '{mode}'. Must be one of: {', '.join(sorted(_VALID_MODES))}"
        )
    return mode  # type: ignore[return-value]


def is_multi_user() -> bool:
    """True when auth mode provides per-user data isolation."""
    return get_auth_mode() in ("local", "ldap")


def require_active(user: Optional[dict]) -> dict:
    """Raise 403 if user is not active. Passthrough for non-multi-user modes."""
    if not is_multi_user():
        return user or {}
    if user is None:
        raise ForbiddenError("Authentication required")
    if user.get("status") != "active":
        raise ForbiddenError("Account is not active")
    return user


def require_admin(user: Optional[dict]) -> dict:
    """Raise 403 if user is not an admin or super_admin."""
    user = require_active(user)
    if not is_multi_user():
        return user
    if user.get("role") not in ("admin", "super_admin"):
        raise ForbiddenError("Administrator privileges required")
    return user


def require_super_admin(user: Optional[dict]) -> dict:
    """Raise 403 if user is not the super_admin."""
    user = require_active(user)
    if not is_multi_user():
        return user
    if user.get("role") != "super_admin":
        raise ForbiddenError("Super-administrator privileges required")
    return user


# -- FastAPI dependencies for router-level guards ─────────────────────


def admin_guard(request: Request) -> None:
    """
    FastAPI dependency: raises 403 for non-admin users in multi-user mode.

    In ``none`` and ``password`` modes this is intentionally a no-op so
    that simple installations retain full access to every endpoint.
    """
    if not is_multi_user():
        return
    user = getattr(request.state, "user", None)
    require_admin(user)
