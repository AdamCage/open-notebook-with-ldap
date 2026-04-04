"""
User management router for administrators.
Provides endpoints to list, approve, deactivate, and manage user roles.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from loguru import logger
from pydantic import BaseModel

from api.auth import get_current_user, invalidate_user_status_cache
from api.auth_config import is_multi_user, require_admin
from open_notebook.domain.app_user import AppUser
from open_notebook.exceptions import ForbiddenError, InvalidInputError, NotFoundError

router = APIRouter(prefix="/users", tags=["users"])

_ALLOWED_STATUS_FILTERS = {"pending", "active", "deactivated"}


class RoleUpdateRequest(BaseModel):
    role: str


# ---------------------------------------------------------------------------
# GET /users
# ---------------------------------------------------------------------------


@router.get("")
async def list_users(
    status: Optional[str] = Query(None, description="Filter by status"),
    user: Optional[dict] = Depends(get_current_user),
):
    """List all users. Admin only."""
    if not is_multi_user():
        raise InvalidInputError("User management is not available in this auth mode")
    require_admin(user)

    if status is not None and status not in _ALLOWED_STATUS_FILTERS:
        raise InvalidInputError(
            f"Invalid status filter '{status}'. "
            f"Must be one of: {', '.join(sorted(_ALLOWED_STATUS_FILTERS))}"
        )

    users = await AppUser.get_all_users(status=status)
    return [u.to_public_dict() for u in users]


# ---------------------------------------------------------------------------
# GET /users/{user_id}
# ---------------------------------------------------------------------------


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    user: Optional[dict] = Depends(get_current_user),
):
    """Get a single user's details. Admin only."""
    if not is_multi_user():
        raise InvalidInputError("User management is not available in this auth mode")
    require_admin(user)

    target = await AppUser.get(user_id)
    if not target:
        raise NotFoundError("User not found")
    return target.to_public_dict()


# ---------------------------------------------------------------------------
# PUT /users/{user_id}/approve
# ---------------------------------------------------------------------------


@router.put("/{user_id}/approve")
async def approve_user(
    user_id: str,
    user: Optional[dict] = Depends(get_current_user),
):
    """Approve a pending user account. Admin only."""
    if not is_multi_user():
        raise InvalidInputError("User management is not available in this auth mode")
    require_admin(user)

    target = await AppUser.get(user_id)
    if not target:
        raise NotFoundError("User not found")
    if target.status != "pending":
        raise InvalidInputError(
            f"Cannot approve user with status '{target.status}'"
        )

    target.status = "active"
    await target.save()
    invalidate_user_status_cache(target.username)
    logger.info("User '%s' approved by '%s'", target.username, user.get("sub"))
    return target.to_public_dict()


# ---------------------------------------------------------------------------
# PUT /users/{user_id}/deactivate
# ---------------------------------------------------------------------------


@router.put("/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    user: Optional[dict] = Depends(get_current_user),
):
    """Deactivate a user account. Admin only. Cannot deactivate super_admin or self."""
    if not is_multi_user():
        raise InvalidInputError("User management is not available in this auth mode")
    require_admin(user)

    target = await AppUser.get(user_id)
    if not target:
        raise NotFoundError("User not found")
    if target.role == "super_admin":
        raise ForbiddenError("Cannot deactivate the super-administrator")
    if target.username == user.get("sub"):
        raise ForbiddenError("Cannot deactivate your own account")
    if target.status == "deactivated":
        raise InvalidInputError("User is already deactivated")

    target.status = "deactivated"
    await target.save()
    invalidate_user_status_cache(target.username)
    logger.info("User '%s' deactivated by '%s'", target.username, user.get("sub"))
    return target.to_public_dict()


# ---------------------------------------------------------------------------
# PUT /users/{user_id}/activate
# ---------------------------------------------------------------------------


@router.put("/{user_id}/activate")
async def activate_user(
    user_id: str,
    user: Optional[dict] = Depends(get_current_user),
):
    """Re-activate a deactivated user. Admin only."""
    if not is_multi_user():
        raise InvalidInputError("User management is not available in this auth mode")
    require_admin(user)

    target = await AppUser.get(user_id)
    if not target:
        raise NotFoundError("User not found")
    if target.status == "active":
        raise InvalidInputError("User is already active")

    target.status = "active"
    await target.save()
    invalidate_user_status_cache(target.username)
    logger.info("User '%s' activated by '%s'", target.username, user.get("sub"))
    return target.to_public_dict()


# ---------------------------------------------------------------------------
# PUT /users/{user_id}/role
# ---------------------------------------------------------------------------


@router.put("/{user_id}/role")
async def update_user_role(
    user_id: str,
    body: RoleUpdateRequest,
    user: Optional[dict] = Depends(get_current_user),
):
    """Change a user's role. Admin only. Super-admin role cannot be changed."""
    if not is_multi_user():
        raise InvalidInputError("User management is not available in this auth mode")
    require_admin(user)

    if body.role not in ("admin", "user"):
        raise InvalidInputError("Role must be 'admin' or 'user'")

    target = await AppUser.get(user_id)
    if not target:
        raise NotFoundError("User not found")
    if target.role == "super_admin":
        raise ForbiddenError("Cannot change the super-administrator's role")

    target.role = body.role
    await target.save()
    logger.info(
        "User '%s' role changed to '%s' by '%s'",
        target.username, body.role, user.get("sub"),
    )
    return target.to_public_dict()
