"""
Authentication router for Open Notebook API.
Provides endpoints for auth status, LDAP authentication, and LDAP admin config.
"""

import asyncio
from ssl import CERT_NONE, CERT_REQUIRED, PROTOCOL_TLS
from typing import Optional

from fastapi import APIRouter, Depends
from ldap3 import NONE as LDAP_NONE
from ldap3 import Connection, Server, Tls
from ldap3.utils.conv import escape_filter_chars
from loguru import logger
from pydantic import BaseModel

from api.auth import check_api_password, create_ldap_jwt
from api.ldap_config import LdapSettings, get_ldap_settings, update_ldap_settings
from open_notebook.exceptions import (
    AuthenticationError,
    ConfigurationError,
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
# GET /auth/status
# ---------------------------------------------------------------------------


@router.get("/status")
async def get_auth_status():
    """Return authentication status including LDAP availability."""
    has_password = bool(get_secret_from_env("OPEN_NOTEBOOK_PASSWORD"))
    ldap_settings = get_ldap_settings()
    auth_enabled = has_password or ldap_settings.enable_ldap

    return {
        "auth_enabled": auth_enabled,
        "ldap_enabled": ldap_settings.enable_ldap,
        "message": (
            "Authentication is required"
            if auth_enabled
            else "Authentication is disabled"
        ),
    }


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
    4. Return a signed JWT on success.
    """
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

        # --- Issue JWT ------------------------------------------------------
        logger.info(f"LDAP authentication successful for user: {form_data.user}")
        try:
            token = create_ldap_jwt(
                username=form_data.user,
                email=email,
                name=cn,
            )
        except (ValueError, ConfigurationError) as e:
            logger.error(f"JWT creation error: {e}")
            raise ConfigurationError(
                "Server misconfiguration: cannot issue session token."
            )

        return {
            "token": token,
            "token_type": "Bearer",
            "user": form_data.user,
            "email": email,
            "name": cn,
        }
    finally:
        for conn in (connection_app, connection_user):
            if conn:
                try:
                    await asyncio.to_thread(conn.unbind)
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Admin endpoints — require password auth
# ---------------------------------------------------------------------------


@router.get("/ldap/config")
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


@router.post("/ldap/config")
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


