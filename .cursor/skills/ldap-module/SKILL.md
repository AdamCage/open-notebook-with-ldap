---
name: ldap-module
description: Develop and maintain the LDAP authentication module. Covers the full auth chain from ldap_config.py through middleware JWT handling, LDAP router endpoints, frontend auth-store, and LoginForm. Use when working with LDAP, authentication, JWT tokens, login flows, or per-user data isolation.
---

# LDAP Authentication Module

## Architecture Overview

```
LoginForm (frontend)
  → auth-store.ldapLogin()
    → POST /api/auth/ldap (api/routers/auth.py)
      → ldap3: TLS config → Server → app bind → search → user bind
      → create_ldap_jwt() (api/auth.py)
    ← JWT token
  → Bearer {JWT} on subsequent requests
    → PasswordAuthMiddleware (api/auth.py)
      → decode JWT → request.state.user
      → get_current_user() / get_owner_id()
```

## Key Files

| Layer | File | Purpose |
|-------|------|---------|
| Config | `api/ldap_config.py` | `LdapSettings` Pydantic model, `get_ldap_settings()` singleton |
| Middleware | `api/auth.py` | `PasswordAuthMiddleware`, JWT decode, `get_current_user`, `get_owner_id` |
| Router | `api/routers/auth.py` | `POST /auth/ldap`, `GET /auth/status`, `GET/POST /auth/ldap/config` |
| Frontend store | `frontend/src/lib/stores/auth-store.ts` | `ldapLogin()`, token persistence |
| Frontend hook | `frontend/src/lib/hooks/use-auth.ts` | `handleLdapLogin()`, i18n error mapping |
| Frontend API | `frontend/src/lib/api/ldap.ts` | `ldapSignIn()`, `getLdapConfig()` |
| Frontend UI | `frontend/src/components/auth/LoginForm.tsx` | LDAP/password mode toggle |
| i18n | `frontend/src/lib/locales/*/index.ts` | `auth.ldapAuthFailed` and related keys |

## LDAP Auth Endpoint Pattern

```python
# In api/routers/auth.py — POST /api/auth/ldap
async def ldap_auth(credentials: LdapLoginRequest):
    settings = get_ldap_settings()
    # 1. Configure TLS (ldap3.Tls)
    # 2. Create Server with connect_timeout=15
    # 3. App bind (LDAP_APP_DN + LDAP_APP_PASSWORD)
    # 4. Search user (escape_filter_chars!)
    # 5. Extract user_dn, email, cn from entry
    # 6. User bind (user_dn + user password)
    # 7. create_ldap_jwt(sub, email, name)
    # ALWAYS: unbind connections in finally block
```

## JWT Token Structure

Claims: `sub` (username), `email`, `name`, `type` ("ldap"), `exp` (24h), `jti` (UUID).
Algorithm: HS256. Secret: `LDAP_JWT_SECRET` or `OPEN_NOTEBOOK_ENCRYPTION_KEY`.

## Error Handling

- Use `AuthenticationError` for 401 (bind fail, user not found)
- Use `ConfigurationError` for 500 (TLS error, missing secret)
- Use `InvalidInputError` for 400 (LDAP disabled, missing email)
- Frontend: store sets `'ldapAuthFailed'` key; hook replaces with `t.auth.ldapAuthFailed`

## Environment Variables

All loaded in `api/ldap_config.py`. Key vars: `ENABLE_LDAP`, `LDAP_SERVER_HOST`, `LDAP_SERVER_PORT`, `LDAP_APP_DN`, `LDAP_APP_PASSWORD`, `LDAP_SEARCH_BASE`, `LDAP_USE_TLS`, `LDAP_JWT_SECRET`. Secrets support `_FILE` suffix (Docker secrets).

## Testing Checklist

- [ ] LDAP disabled: system works exactly as before
- [ ] LDAP enabled without password: requires valid JWT
- [ ] LDAP + password coexistence: login page shows both modes
- [ ] Connection cleanup: `unbind()` called in all code paths
- [ ] Owner isolation: LDAP user data invisible to other users
