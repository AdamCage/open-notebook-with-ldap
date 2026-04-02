import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from open_notebook.exceptions import ConfigurationError
from open_notebook.utils.encryption import get_secret_from_env

JWT_ALGORITHM = "HS256"
LDAP_TOKEN_EXPIRY_HOURS = 24


def get_jwt_secret() -> Optional[str]:
    """
    Return the secret used to sign/verify LDAP JWT tokens.
    Checks LDAP_JWT_SECRET first, falls back to OPEN_NOTEBOOK_ENCRYPTION_KEY.
    """
    secret = get_secret_from_env("LDAP_JWT_SECRET")
    if secret:
        return secret
    return get_secret_from_env("OPEN_NOTEBOOK_ENCRYPTION_KEY")


def create_ldap_jwt(username: str, email: str, name: str) -> str:
    """Create a signed JWT for an LDAP-authenticated user."""
    secret = get_jwt_secret()
    if not secret:
        raise ConfigurationError(
            "No JWT secret configured. "
            "Set LDAP_JWT_SECRET or OPEN_NOTEBOOK_ENCRYPTION_KEY."
        )
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "email": email,
        "name": name,
        "type": "ldap",
        "iat": now,
        "exp": now + timedelta(hours=LDAP_TOKEN_EXPIRY_HOURS),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def verify_ldap_jwt(token: str) -> dict:
    """
    Decode and verify an LDAP JWT token.
    Returns the payload dict on success, raises jwt.InvalidTokenError on failure.
    """
    secret = get_jwt_secret()
    if not secret:
        raise jwt.InvalidTokenError("No JWT secret configured")
    payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    if payload.get("type") != "ldap":
        raise jwt.InvalidTokenError("Token is not an LDAP token")
    return payload


def _is_valid_credential(credentials: str, password: Optional[str]) -> bool:
    """Check if credentials match the configured password or a valid LDAP JWT."""
    if password and credentials == password:
        return True
    try:
        verify_ldap_jwt(credentials)
        return True
    except Exception:
        return False


def _extract_user_identity(credentials: str, password: Optional[str]) -> dict:
    """Extract user identity from valid credentials. Returns a user dict."""
    if password and credentials == password:
        return {"sub": "__password__", "type": "password"}
    try:
        payload = verify_ldap_jwt(credentials)
        return {
            "sub": payload.get("sub"),
            "email": payload.get("email"),
            "name": payload.get("name"),
            "type": "ldap",
        }
    except Exception:
        return {"sub": "__password__", "type": "password"}


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


class PasswordAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to check password authentication for all API requests.
    Accepts either the configured password or a valid LDAP JWT as Bearer token.
    Supports Docker secrets via OPEN_NOTEBOOK_PASSWORD_FILE.
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
        if self.password:
            return True
        from api.ldap_config import get_ldap_settings

        return get_ldap_settings().enable_ldap

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

        if not _is_valid_credential(credentials, self.password):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid credentials"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Set user identity on request state for downstream access
        request.state.user = _extract_user_identity(credentials, self.password)

        response = await call_next(request)
        return response


security = HTTPBearer(auto_error=False)


def check_api_password(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> bool:
    """
    Utility dependency: accepts the configured password or a valid LDAP JWT.
    Returns True without checking if neither password nor LDAP is configured.
    """
    password = get_secret_from_env("OPEN_NOTEBOOK_PASSWORD")

    from api.ldap_config import get_ldap_settings

    ldap_enabled = get_ldap_settings().enable_ldap

    if not password and not ldap_enabled:
        return True

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not _is_valid_credential(credentials.credentials, password):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True
