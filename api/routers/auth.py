"""
Authentication router for Open Notebook API.
Provides endpoints for auth status, local registration/login, profile management,
LDAP authentication, and LDAP admin config.
"""

import asyncio
import os
from datetime import datetime, timezone
from ssl import CERT_NONE, CERT_REQUIRED, PROTOCOL_TLS
from typing import Optional

from fastapi import APIRouter, Depends
from ldap3 import NONE as LDAP_NONE
from ldap3 import Connection, Server, Tls
from ldap3.utils.conv import escape_filter_chars
from loguru import logger
from pydantic import BaseModel

from api.auth import (
    check_api_password,
    create_ldap_jwt,
    create_user_jwt,
    get_current_user,
)
from api.auth_config import admin_guard, get_auth_mode, is_multi_user, require_active
from api.ldap_config import LdapSettings, get_ldap_settings, update_ldap_settings
from open_notebook.domain.app_user import AppUser
from open_notebook.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ForbiddenError,
    InvalidInputError,
)
from open_notebook.utils.encryption import get_secret_from_env

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class LdapLoginRequest(BaseModel):
    user: str
    password: str


class LocalRegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    display_name: Optional[str] = None


class LocalLoginRequest(BaseModel):
    username: str
    password: str


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class LdapServerConfig(BaseModel):
    label: str = "LDAP Server"
    host: str = "localhost"
    port: int = 389
    attribute_for_mail: str = "mail"
    attribute_for_username: str = "uid"
    app_dn: str = ""
    app_dn_password: str = ""
    search_base: str = ""
    search_filters: str = ""
    use_tls: bool = True
    ca_cert_file: Optional[str] = ""
    validate_cert: bool = True
    ciphers: Optional[str] = "ALL"


# ---------------------------------------------------------------------------
# GET /auth/status  (public)
# ---------------------------------------------------------------------------


@router.get("/status")
async def get_auth_status():
    """Return authentication status including mode and capabilities."""
    auth_mode = get_auth_mode()
    ldap_settings = get_ldap_settings()

    if auth_mode == "none":
        auth_enabled = False
    elif auth_mode == "password":
        auth_enabled = bool(get_secret_from_env("OPEN_NOTEBOOK_PASSWORD"))
    else:
        auth_enabled = True

    return {
        "auth_enabled": auth_enabled,
        "auth_mode": auth_mode,
        "ldap_enabled": auth_mode == "ldap" and ldap_settings.enable_ldap,
        "registration_enabled": auth_mode == "local",
        "message": (
            "Authentication is required"
            if auth_enabled
            else "Authentication is disabled"
        ),
    }


# ---------------------------------------------------------------------------
# POST /auth/register  (public — only AUTH_MODE=local)
# ---------------------------------------------------------------------------


@router.post("/register", status_code=201)
async def register_user(form_data: LocalRegisterRequest):
    """Register a new local user account (requires admin approval)."""
    if get_auth_mode() != "local":
        raise InvalidInputError("Registration is not enabled in this auth mode")

    if len(form_data.password) < 6:
        raise InvalidInputError("Password must be at least 6 characters")

    existing_username = await AppUser.get_by_username(form_data.username)
    if existing_username:
        raise InvalidInputError("Username is already taken")

    existing_email = await AppUser.get_by_email(form_data.email)
    if existing_email:
        raise InvalidInputError("Email is already registered")

    user = AppUser(
        username=form_data.username,
        email=form_data.email,
        display_name=form_data.display_name or form_data.username,
        role="user",
        status="pending",
        auth_provider="local",
    )
    user.set_password(form_data.password)
    await user.save()

    logger.info("New user registered (pending approval): %s", form_data.username)
    return {
        "message": "Registration successful. Your account is awaiting administrator approval.",
        "username": user.username,
        "status": user.status,
    }


# ---------------------------------------------------------------------------
# POST /auth/login  (public — only AUTH_MODE=local)
# ---------------------------------------------------------------------------


@router.post("/login")
async def local_login(form_data: LocalLoginRequest):
    """Authenticate with username and password (local accounts)."""
    if get_auth_mode() != "local":
        raise InvalidInputError("Local login is not enabled in this auth mode")

    user = await AppUser.get_by_username(form_data.username)
    if not user or not user.verify_password(form_data.password):
        raise AuthenticationError("Invalid username or password")

    if user.status == "pending":
        raise ForbiddenError("Your account is awaiting administrator approval")

    if user.status == "deactivated":
        raise ForbiddenError("Your account has been deactivated")

    user.last_login = datetime.now(timezone.utc)
    await user.save()

    token = create_user_jwt(
        username=user.username,
        email=user.email,
        name=user.display_name or user.username,
        role=user.role,
        status=user.status,
    )

    return {
        "token": token,
        "token_type": "Bearer",
        "user": user.to_public_dict(),
    }


# ---------------------------------------------------------------------------
# GET /auth/me  (authenticated)
# ---------------------------------------------------------------------------


@router.get("/me")
async def get_my_profile(user: Optional[dict] = Depends(get_current_user)):
    """Return the current user's profile."""
    if not is_multi_user():
        return {"message": "Profile not available in this auth mode"}

    if user is None:
        raise AuthenticationError("Not authenticated")

    db_user = await AppUser.get_by_username(user["sub"])
    if not db_user:
        raise AuthenticationError("User not found")

    return db_user.to_public_dict()


# ---------------------------------------------------------------------------
# PUT /auth/me  (authenticated, local only)
# ---------------------------------------------------------------------------


@router.put("/me")
async def update_my_profile(
    body: UpdateProfileRequest,
    user: Optional[dict] = Depends(get_current_user),
):
    """Update the current user's display name and/or email (local mode only)."""
    require_active(user)
    if get_auth_mode() != "local":
        raise InvalidInputError("Profile editing is only available in local auth mode")

    db_user = await AppUser.get_by_username(user["sub"])
    if not db_user:
        raise AuthenticationError("User not found")

    if body.display_name is not None:
        db_user.display_name = body.display_name
    if body.email is not None:
        if body.email != db_user.email:
            conflict = await AppUser.get_by_email(body.email)
            if conflict and conflict.id != db_user.id:
                raise InvalidInputError("Email is already registered")
            db_user.email = body.email

    await db_user.save()
    return db_user.to_public_dict()


# ---------------------------------------------------------------------------
# PUT /auth/me/password  (authenticated, local only)
# ---------------------------------------------------------------------------


@router.put("/me/password")
async def change_my_password(
    body: ChangePasswordRequest,
    user: Optional[dict] = Depends(get_current_user),
):
    """Change the current user's password (local mode only)."""
    require_active(user)
    if get_auth_mode() != "local":
        raise InvalidInputError("Password change is only available in local auth mode")

    db_user = await AppUser.get_by_username(user["sub"])
    if not db_user:
        raise AuthenticationError("User not found")

    if not db_user.verify_password(body.current_password):
        raise AuthenticationError("Current password is incorrect")

    if len(body.new_password) < 6:
        raise InvalidInputError("New password must be at least 6 characters")

    db_user.set_password(body.new_password)
    await db_user.save()
    return {"message": "Password changed successfully"}


# ---------------------------------------------------------------------------
# POST /auth/ldap  (public — excluded from password middleware)
# ---------------------------------------------------------------------------


@router.post("/ldap")
async def ldap_auth(form_data: LdapLoginRequest):
    """
    Authenticate a user via LDAP.

    1. Bind with service-account credentials (or anonymous).
    2. Search for the user by username attribute.
    3. Bind again as the found user DN + supplied password.
    4. Auto-register / update AppUser record.
    5. Return a signed JWT on success.
    """
    if get_auth_mode() != "ldap":
        raise InvalidInputError("LDAP authentication is not enabled in this auth mode")

    settings = get_ldap_settings()

    if not settings.enable_ldap:
        raise InvalidInputError("LDAP authentication is not enabled")

    # --- TLS ---------------------------------------------------------------
    try:
        tls = Tls(
            validate=CERT_REQUIRED if settings.validate_cert else CERT_NONE,
            version=PROTOCOL_TLS,
            ca_certs_file=settings.ca_cert_file or None,
            ciphers=settings.ciphers or "ALL",
        )
    except Exception as e:
        logger.error(f"LDAP TLS configuration error: {e}")
        raise ConfigurationError("Failed to configure TLS for LDAP connection.")

    server = Server(
        host=settings.server_host,
        port=settings.server_port,
        get_info=LDAP_NONE,
        use_ssl=settings.use_tls,
        tls=tls,
        connect_timeout=15,
    )

    connection_app = None
    connection_user = None
    try:
        # --- Server + app bind ---------------------------------------------
        try:
            auth_type = "SIMPLE" if settings.app_dn else "ANONYMOUS"
            connection_app = Connection(
                server,
                settings.app_dn,
                settings.app_password,
                auto_bind="NONE",
                authentication=auth_type,
            )

            logger.info(
                f"LDAP connecting to {settings.server_host}:{settings.server_port} "
                f"(TLS={settings.use_tls}, auth={auth_type})"
            )

            if not await asyncio.to_thread(connection_app.bind):
                logger.warning("LDAP application account bind failed")
                raise ConfigurationError("LDAP application account bind failed")
        except (ConfigurationError, AuthenticationError, InvalidInputError):
            raise
        except Exception as e:
            logger.error(f"LDAP connection error: {e}")
            raise ConfigurationError("Failed to connect to LDAP server.")

        # --- Search user ---------------------------------------------------
        try:
            username_attr = settings.attribute_for_username
            mail_attr = settings.attribute_for_mail
            escaped_user = escape_filter_chars(form_data.user.lower())
            search_filter = (
                f"(&({username_attr}={escaped_user}){settings.search_filters})"
            )

            logger.info(f"LDAP searching: base={settings.search_base}, filter={search_filter}")

            search_ok = await asyncio.to_thread(
                connection_app.search,
                search_base=settings.search_base,
                search_filter=search_filter,
                attributes=[username_attr, mail_attr, "cn"],
            )

            if not search_ok or not connection_app.entries:
                logger.warning(f"LDAP user not found: {form_data.user}")
                raise AuthenticationError("User not found in the LDAP server")

            entry = connection_app.entries[0]

            entry_username = entry[username_attr].value
            if isinstance(entry_username, list):
                username_list = [str(n).lower() for n in entry_username]
            else:
                username_list = [str(entry_username).lower()]

            email_raw = entry[mail_attr].value
            if not email_raw:
                raise InvalidInputError("User does not have a valid email address.")
            email = (
                email_raw[0].lower()
                if isinstance(email_raw, list)
                else str(email_raw).lower()
            )

            cn_value = entry["cn"].value
            cn = cn_value[0] if isinstance(cn_value, list) else str(cn_value)
            user_dn = entry.entry_dn

        except (ConfigurationError, AuthenticationError, InvalidInputError):
            raise
        except Exception as e:
            logger.error(f"LDAP search error: {e}")
            raise ConfigurationError("LDAP search failed.")

        # --- Verify username matches ---------------------------------------
        if form_data.user.lower() not in username_list:
            raise AuthenticationError("User record mismatch.")

        # --- User bind (password verification) -----------------------------
        try:
            connection_user = Connection(
                server,
                user_dn,
                form_data.password,
                auto_bind="NONE",
                authentication="SIMPLE",
            )
            if not await asyncio.to_thread(connection_user.bind):
                logger.warning(f"LDAP user bind failed for DN: {user_dn}")
                raise AuthenticationError("Authentication failed.")
        except (ConfigurationError, AuthenticationError, InvalidInputError):
            raise
        except Exception as e:
            logger.error(f"LDAP user bind error: {e}")
            raise AuthenticationError("Authentication failed.")

        # --- Auto-register / update AppUser --------------------------------
        app_user = await _upsert_ldap_user(form_data.user.lower(), email, cn)

        if app_user.status == "deactivated":
            raise ForbiddenError("Your account has been deactivated")

        # --- Issue JWT ------------------------------------------------------
        logger.info(f"LDAP authentication successful for user: {form_data.user}")
        try:
            token = create_ldap_jwt(
                username=app_user.username,
                email=app_user.email,
                name=app_user.display_name or cn,
                role=app_user.role,
            )
        except (ValueError, ConfigurationError) as e:
            logger.error(f"JWT creation error: {e}")
            raise ConfigurationError(
                "Server misconfiguration: cannot issue session token."
            )

        return {
            "token": token,
            "token_type": "Bearer",
            "user": app_user.to_public_dict(),
        }
    finally:
        for conn in (connection_app, connection_user):
            if conn:
                try:
                    await asyncio.to_thread(conn.unbind)
                except Exception:
                    pass


async def _upsert_ldap_user(username: str, email: str, display_name: str) -> AppUser:
    """Create or update an AppUser record after successful LDAP authentication."""
    admin_username = os.environ.get("ADMIN_USERNAME", "").strip().lower()

    existing = await AppUser.get_by_username(username)
    if existing:
        existing.email = email
        existing.display_name = display_name
        existing.last_login = datetime.now(timezone.utc)
        if username == admin_username and existing.role != "super_admin":
            existing.role = "super_admin"
            existing.status = "active"
            logger.info("Promoted LDAP user '%s' to super_admin", username)
        await existing.save()
        return existing

    role = "super_admin" if username == admin_username else "user"
    new_user = AppUser(
        username=username,
        email=email,
        display_name=display_name,
        role=role,
        status="active",
        auth_provider="ldap",
        last_login=datetime.now(timezone.utc),
    )
    await new_user.save()
    logger.info("Auto-registered LDAP user '%s' (role=%s)", username, role)
    return new_user


# ---------------------------------------------------------------------------
# Admin endpoints — require password auth
# ---------------------------------------------------------------------------


@router.get("/ldap/config", dependencies=[Depends(admin_guard)])
async def get_ldap_config(_: bool = Depends(check_api_password)):
    """Return current LDAP configuration (password masked)."""
    settings = get_ldap_settings()
    return {
        "enable_ldap": settings.enable_ldap,
        "label": settings.server_label,
        "host": settings.server_host,
        "port": settings.server_port,
        "attribute_for_mail": settings.attribute_for_mail,
        "attribute_for_username": settings.attribute_for_username,
        "app_dn": settings.app_dn,
        "app_dn_password": "********" if settings.app_password else "",
        "search_base": settings.search_base,
        "search_filters": settings.search_filters,
        "use_tls": settings.use_tls,
        "ca_cert_file": settings.ca_cert_file,
        "validate_cert": settings.validate_cert,
        "ciphers": settings.ciphers,
    }


@router.post("/ldap/config", dependencies=[Depends(admin_guard)])
async def update_ldap_config(
    form_data: LdapServerConfig,
    _: bool = Depends(check_api_password),
):
    """Update LDAP server configuration at runtime (lost on restart)."""
    settings = get_ldap_settings()
    new_settings = LdapSettings(
        enable_ldap=settings.enable_ldap,
        server_label=form_data.label,
        server_host=form_data.host,
        server_port=form_data.port,
        attribute_for_mail=form_data.attribute_for_mail,
        attribute_for_username=form_data.attribute_for_username,
        app_dn=form_data.app_dn,
        app_password=form_data.app_dn_password or settings.app_password,
        search_base=form_data.search_base,
        search_filters=form_data.search_filters,
        use_tls=form_data.use_tls,
        ca_cert_file=form_data.ca_cert_file or "",
        validate_cert=form_data.validate_cert,
        ciphers=form_data.ciphers or "ALL",
    )
    update_ldap_settings(new_settings)

    return {
        "label": new_settings.server_label,
        "host": new_settings.server_host,
        "port": new_settings.server_port,
        "attribute_for_mail": new_settings.attribute_for_mail,
        "attribute_for_username": new_settings.attribute_for_username,
        "app_dn": new_settings.app_dn,
        "app_dn_password": "********" if new_settings.app_password else "",
        "search_base": new_settings.search_base,
        "search_filters": new_settings.search_filters,
        "use_tls": new_settings.use_tls,
        "ca_cert_file": new_settings.ca_cert_file,
        "validate_cert": new_settings.validate_cert,
        "ciphers": new_settings.ciphers,
    }
