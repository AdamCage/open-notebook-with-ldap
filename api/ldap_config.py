"""
LDAP authentication configuration.

Loads LDAP settings from environment variables with sensible defaults.
When ENABLE_LDAP is false (default), the rest of the settings are ignored.
"""

import os
from functools import lru_cache
from typing import Optional

from pydantic import BaseModel, field_validator

from open_notebook.utils.encryption import get_secret_from_env


class LdapSettings(BaseModel):
    enable_ldap: bool = False
    server_label: str = "LDAP Server"
    server_host: str = "localhost"
    server_port: int = 389
    attribute_for_mail: str = "mail"
    attribute_for_username: str = "uid"
    app_dn: str = ""
    app_password: str = ""
    search_base: str = ""
    search_filters: str = ""
    use_tls: bool = True
    ca_cert_file: str = ""
    validate_cert: bool = True
    ciphers: str = "ALL"

    @field_validator("server_port")
    @classmethod
    def port_in_range(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError("LDAP_SERVER_PORT must be between 1 and 65535")
        return v


def _load_ldap_settings() -> LdapSettings:
    def _bool_env(var: str, default: bool) -> bool:
        val = os.environ.get(var, "").strip().lower()
        if not val:
            return default
        return val in ("true", "1", "yes")

    return LdapSettings(
        enable_ldap=_bool_env("ENABLE_LDAP", False),
        server_label=os.environ.get("LDAP_SERVER_LABEL", "LDAP Server"),
        server_host=os.environ.get("LDAP_SERVER_HOST", "localhost"),
        server_port=int(os.environ.get("LDAP_SERVER_PORT", "389")),
        attribute_for_mail=os.environ.get("LDAP_ATTRIBUTE_FOR_MAIL", "mail"),
        attribute_for_username=os.environ.get(
            "LDAP_ATTRIBUTE_FOR_USERNAME", "uid"
        ),
        app_dn=os.environ.get("LDAP_APP_DN", ""),
        app_password=get_secret_from_env("LDAP_APP_PASSWORD") or "",
        search_base=os.environ.get("LDAP_SEARCH_BASE", ""),
        search_filters=os.environ.get("LDAP_SEARCH_FILTERS", ""),
        use_tls=_bool_env("LDAP_USE_TLS", True),
        ca_cert_file=os.environ.get("LDAP_CA_CERT_FILE", ""),
        validate_cert=_bool_env("LDAP_VALIDATE_CERT", True),
        ciphers=os.environ.get("LDAP_CIPHERS", "ALL"),
    )


_ldap_settings: Optional[LdapSettings] = None


def get_ldap_settings() -> LdapSettings:
    """Return the cached LDAP settings singleton, loading from env on first call."""
    global _ldap_settings
    if _ldap_settings is None:
        _ldap_settings = _load_ldap_settings()
    return _ldap_settings


def update_ldap_settings(new_settings: LdapSettings) -> LdapSettings:
    """Replace the cached settings (runtime-only, lost on restart)."""
    global _ldap_settings
    _ldap_settings = new_settings
    return _ldap_settings
