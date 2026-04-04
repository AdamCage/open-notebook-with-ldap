import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from open_notebook.exceptions import ConfigurationError
from open_notebook.utils.encryption import get_secret_from_env

JWT_ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 24

# TTL cache for user active-status checks to avoid a DB hit on every request.
# Maps username -> (timestamp, is_active).
_USER_STATUS_CACHE: dict[str, tuple[float, bool]] = {}
_STATUS_CACHE_TTL_SECONDS = 60


def _check_user_status_cached(username: str, is_active: bool) -> None:
    """Store a user's active status in the TTL cache."""
    _USER_STATUS_CACHE[username] = (time.monotonic(), is_active)


def _get_cached_user_status(username: str) -> Optional[bool]:
    """Return cached is_active, or None if expired / missing."""
    entry = _USER_STATUS_CACHE.get(username)
    if entry is None:
        return None
    ts, is_active = entry
    if time.monotonic() - ts > _STATUS_CACHE_TTL_SECONDS:
        del _USER_STATUS_CACHE[username]
        return None
    return is_active


def invalidate_user_status_cache(username: str) -> None:
    """Remove a user from the status cache (call after approve/deactivate)."""
    _USER_STATUS_CACHE.pop(username, None)


def get_jwt_secret() -> Optional[str]:
    """
    Return the secret used to sign/verify JWT tokens.
    Priority: JWT_SECRET > LDAP_JWT_SECRET > OPEN_NOTEBOOK_ENCRYPTION_KEY.
    """
    secret = get_secret_from_env("JWT_SECRET")
    if secret:
        return secret
    secret = get_secret_from_env("LDAP_JWT_SECRET")
    if secret:
        return secret
    return get_secret_from_env("OPEN_NOTEBOOK_ENCRYPTION_KEY")


# -- JWT creation / verification ──────────────────────────────────────


def create_ldap_jwt(username: str, email: str, name: str, role: str = "user") -> str:
    """Create a signed JWT for an LDAP-authenticated user."""
    secret = get_jwt_secret()
    if not secret:
        raise ConfigurationError(
            "No JWT secret configured. "
            "Set JWT_SECRET, LDAP_JWT_SECRET, or OPEN_NOTEBOOK_ENCRYPTION_KEY."
        )
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "email": email,
        "name": name,
        "role": role,
        "type": "ldap",
        "iat": now,
        "exp": now + timedelta(hours=TOKEN_EXPIRY_HOURS),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def create_user_jwt(
    username: str, email: str, name: str, role: str = "user", status: str = "active"
) -> str:
    """Create a signed JWT for a locally-authenticated user."""
    secret = get_jwt_secret()
    if not secret:
        raise ConfigurationError(
            "No JWT secret configured. Set JWT_SECRET or OPEN_NOTEBOOK_ENCRYPTION_KEY."
        )
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "email": email,
        "name": name,
        "role": role,
        "status": status,
        "type": "local",
        "iat": now,
        "exp": now + timedelta(hours=TOKEN_EXPIRY_HOURS),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str) -> dict:
    """
    Decode and verify a JWT token (local or LDAP).
    Returns the payload dict on success, raises jwt.InvalidTokenError on failure.
    """
    secret = get_jwt_secret()
    if not secret:
        raise jwt.InvalidTokenError("No JWT secret configured")
    payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    token_type = payload.get("type")
    if token_type not in ("ldap", "local"):
        raise jwt.InvalidTokenError(f"Unknown token type: {token_type}")
    return payload


def verify_ldap_jwt(token: str) -> dict:
    """Backward-compatible wrapper: decode LDAP-only JWT."""
    payload = verify_jwt(token)
    if payload.get("type") != "ldap":
        raise jwt.InvalidTokenError("Token is not an LDAP token")
    return payload


# -- Credential helpers ───────────────────────────────────────────────


def _is_valid_credential(credentials: str, password: Optional[str]) -> bool:
    """Check if credentials match the configured password or a valid JWT."""
    if password and credentials == password:
        return True
    try:
        verify_jwt(credentials)
        return True
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError, jwt.DecodeError, KeyError):
        return False


def _extract_user_identity(credentials: str, password: Optional[str]) -> dict:
    """Extract user identity from valid credentials. Returns a user dict."""
    if password and credentials == password:
        return {"sub": "__password__", "type": "password", "role": "admin"}
    try:
        payload = verify_jwt(credentials)
        return {
            "sub": payload.get("sub"),
            "email": payload.get("email"),
            "name": payload.get("name"),
            "role": payload.get("role", "user"),
            "status": payload.get("status", "active"),
            "type": payload.get("type"),
        }
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError, jwt.DecodeError, KeyError):
        # Fallback: grant minimal non-admin identity to avoid privilege escalation
        return {"sub": "__anonymous__", "type": "unknown", "role": "user"}


# -- FastAPI dependencies ─────────────────────────────────────────────


def get_current_user(request: Request) -> Optional[dict]:
    """
    FastAPI dependency that returns the current user dict from request.state.
    Returns None when auth is disabled (dev mode).
    """
    return getattr(request.state, "user", None)


def get_owner_id(user: Optional[dict]) -> Optional[str]:
    """
    Derive the owner identifier from a user dict.
    Returns None when auth is disabled (no filtering applied).
    Returns the user's 'sub' claim for scoping data.
    """
    if user is None:
        return None
    return user.get("sub")


# -- Middleware ────────────────────────────────────────────────────────


class PasswordAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware handling authentication for all API requests.

    Supports four AUTH_MODE values:
      none     - no auth, user=None
      password - shared password (OPEN_NOTEBOOK_PASSWORD)
      local    - JWT issued at /auth/login
      ldap     - JWT issued at /auth/ldap
    """

    def __init__(self, app, excluded_paths: Optional[list] = None):
        super().__init__(app)
        self.password = get_secret_from_env("OPEN_NOTEBOOK_PASSWORD")
        self.excluded_paths = excluded_paths or [
            "/",
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
        ]

    def _is_auth_required(self) -> bool:
        from api.auth_config import get_auth_mode

        mode = get_auth_mode()
        if mode == "none":
            return False
        if mode in ("local", "ldap"):
            return True
        # mode == "password"
        return bool(self.password)

    async def dispatch(self, request: Request, call_next):
        if not self._is_auth_required():
            request.state.user = None
            return await call_next(request)

        if request.url.path in self.excluded_paths:
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing authorization header"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            scheme, credentials = auth_header.split(" ", 1)
            if scheme.lower() != "bearer":
                raise ValueError("Invalid authentication scheme")
        except ValueError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid authorization header format"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        from api.auth_config import get_auth_mode

        mode = get_auth_mode()

        if mode == "password":
            if not _is_valid_credential(credentials, self.password):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid credentials"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
            request.state.user = _extract_user_identity(credentials, self.password)
        else:
            # local / ldap -- only JWT accepted
            try:
                payload = verify_jwt(credentials)
            except (jwt.InvalidTokenError, jwt.ExpiredSignatureError, jwt.DecodeError, KeyError):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or expired token"},
                    headers={"WWW-Authenticate": "Bearer"},
                )

            username = payload.get("sub")

            # Verify the user is still active in the DB (with TTL cache)
            cached_status = _get_cached_user_status(username)
            if cached_status is None:
                from open_notebook.domain.app_user import AppUser

                db_user = await AppUser.get_by_username(username)
                is_active = db_user is not None and db_user.is_active
                _check_user_status_cached(username, is_active)
                cached_status = is_active

            if not cached_status:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Account deactivated or not found"},
                    headers={"WWW-Authenticate": "Bearer"},
                )

            request.state.user = {
                "sub": username,
                "email": payload.get("email"),
                "name": payload.get("name"),
                "role": payload.get("role", "user"),
                "status": payload.get("status", "active"),
                "type": payload.get("type"),
            }

        response = await call_next(request)
        return response


security = HTTPBearer(auto_error=False)


def check_api_password(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> bool:
    """
    Utility dependency: accepts the configured password or a valid JWT.
    Returns True without checking if auth is not required.
    """
    from api.auth_config import get_auth_mode

    mode = get_auth_mode()
    if mode == "none":
        return True
    if mode == "password" and not get_secret_from_env("OPEN_NOTEBOOK_PASSWORD"):
        return True

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization",
            headers={"WWW-Authenticate": "Bearer"},
        )

    password = get_secret_from_env("OPEN_NOTEBOOK_PASSWORD") if mode == "password" else None
    if not _is_valid_credential(credentials.credentials, password):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True
