---
name: LDAP Review Fixes
overview: "Address all issues from review_v1.md: fix the broken LDAP-only mode, implement per-user data isolation across the full stack (domain models, DB migration, middleware identity, query filtering, routers), close LDAP connections properly, switch to custom exceptions, and fix smaller code quality issues."
todos:
  - id: p1-ldap-only
    content: "Fix LDAP-only mode: update middleware dispatch + check_api_password to require JWT when ENABLE_LDAP=true, fix auth_enabled in GET /status, fix docs"
    status: completed
  - id: p1-unbind
    content: Add try/finally with connection.unbind() for both LDAP connections in ldap_auth()
    status: completed
  - id: p1-timeout
    content: Add connect_timeout=15 to LDAP Server() constructor
    status: completed
  - id: p2-middleware-user
    content: Extract user identity from JWT/password in middleware, set request.state.user, create get_current_user dependency
    status: completed
  - id: p2-owner-model
    content: Add owner field to ObjectModel, update get_all() with optional owner filter
    status: completed
  - id: p2-migration
    content: Create migration 15.surrealql + 15_down.surrealql (owner fields + indexes), register in async_migrate.py
    status: completed
  - id: p2-search-fn
    content: Update fn::text_search and fn::vector_search in migration 15 to accept and filter by $owner parameter
    status: completed
  - id: p2-routers-scope
    content: Update all data routers (notebooks, sources, notes, insights, chat, source_chat, podcasts, context, search) for owner scoping
    status: completed
  - id: p3-exceptions
    content: Replace HTTPException with AuthenticationError/ConfigurationError/InvalidInputError in auth.py and routers/auth.py
    status: completed
  - id: p3-cn-fix
    content: "Fix fragile cn extraction: use entry['cn'].value instead of str(entry['cn'])"
    status: completed
  - id: p3-i18n-fix
    content: Use ldapAuthFailed i18n key in use-auth.ts instead of hardcoded string in auth-store.ts
    status: completed
  - id: p3-remove-toggle
    content: Remove POST /api/auth/ldap/toggle endpoint
    status: completed
  - id: p3-env-normalize
    content: Remove LDAP_SEARCH_FILTER singular alias from ldap_config.py
    status: completed
isProject: false
---

# LDAP Review Fixes

This plan addresses every issue from [review_v1.md](review_v1.md), organized into three phases: critical security fixes, per-user data isolation (the biggest piece), and code quality improvements.

Recommended agents from `.cursor/rules/` are noted per section.

---

## Phase 1: Critical Security Fixes

**Agents:** `security-engineer`, `backend-architect`

### 1.1 Fix LDAP-only mode (review 3.2)

The middleware in [api/auth.py](api/auth.py) currently skips ALL auth when `OPEN_NOTEBOOK_PASSWORD` is unset. When `ENABLE_LDAP=true` without a password, JWT tokens are issued but never checked.

**Fix in `PasswordAuthMiddleware.__init_`_:** read LDAP config at init time. **Fix in `dispatch`:** change the early-return condition:

```python
# BEFORE (broken):
if not self.password:
    return await call_next(request)

# AFTER:
from api.ldap_config import get_ldap_settings
ldap_enabled = get_ldap_settings().enable_ldap

if not self.password and not ldap_enabled:
    return await call_next(request)
```

Same fix in `check_api_password()`: when no password is set but LDAP is enabled, still require a valid JWT Bearer token.

Also fix `GET /auth/status` in [api/routers/auth.py](api/routers/auth.py) -- the `auth_enabled` field must return `true` when LDAP is enabled even without a password:

```python
auth_enabled = bool(password) or ldap_settings.enable_ldap
```

Fix the incorrect claim in [docs/5-CONFIGURATION/security.md](docs/5-CONFIGURATION/security.md).

### 1.2 Close LDAP connections (review 5.2)

In [api/routers/auth.py](api/routers/auth.py) `ldap_auth()`, both `connection_app` and `connection_user` are never unbound. Wrap in `try/finally`:

```python
connection_app = None
connection_user = None
try:
    connection_app = Connection(server, ...)
    await asyncio.to_thread(connection_app.bind)
    # ... search ...
    connection_user = Connection(server, user_dn, ...)
    await asyncio.to_thread(connection_user.bind)
    # ... success ...
finally:
    if connection_app:
        try:
            await asyncio.to_thread(connection_app.unbind)
        except Exception:
            pass
    if connection_user:
        try:
            await asyncio.to_thread(connection_user.unbind)
        except Exception:
            pass
```

### 1.3 Add LDAP connection timeout (review 6.2, rec 5)

Add `connect_timeout=15` to `Server()` in [api/routers/auth.py](api/routers/auth.py):

```python
server = Server(
    host=settings.server_host,
    port=settings.server_port,
    get_info=LDAP_NONE,
    use_ssl=settings.use_tls,
    tls=tls,
    connect_timeout=15,
)
```

---

## Phase 2: Per-User Data Isolation (review 3.1)

**Agents:** `security-engineer`, `backend-architect`, `software-architect`

This is the largest change, touching domain models, DB schema, middleware, all data-serving routers, search functions, and the frontend auth store.

### 2.1 Middleware: extract user identity into `request.state`

In [api/auth.py](api/auth.py), after successful credential validation, set `request.state.user`:

- **Password auth**: set `request.state.user = {"sub": "__password__", "type": "password"}` (single shared user)
- **LDAP JWT auth**: decode the JWT and set `request.state.user = payload` (contains `sub`, `email`, `name`, `type`)

Add a FastAPI dependency `get_current_user(request: Request)` that reads `request.state.user` and returns a typed dict. Routers import this dependency.

### 2.2 Add `owner` field to domain models

In [open_notebook/domain/base.py](open_notebook/domain/base.py), add `owner: Optional[str] = None` to `ObjectModel`. Update `get_all()` to accept optional `owner` filter:

```python
@classmethod
async def get_all(cls, order_by=None, owner=None):
    where = f"WHERE owner = '{owner}'" if owner else ""
    query = f"SELECT * FROM {cls.table_name} {where}"
    if order_by:
        query += f" ORDER BY {order_by}"
    ...
```

Models affected: `Notebook`, `Source`, `Note`, `ChatSession`, `SourceInsight`, `SourceEmbedding`.

### 2.3 Database migration (15.surrealql)

Create [open_notebook/database/migrations/15.surrealql](open_notebook/database/migrations/15.surrealql):

```sql
-- Migration 15: Add owner field for multi-user data isolation
DEFINE FIELD IF NOT EXISTS owner ON TABLE notebook TYPE option<string>;
DEFINE FIELD IF NOT EXISTS owner ON TABLE source TYPE option<string>;
DEFINE FIELD IF NOT EXISTS owner ON TABLE note TYPE option<string>;
DEFINE FIELD IF NOT EXISTS owner ON TABLE chat_session TYPE option<string>;
DEFINE FIELD IF NOT EXISTS owner ON TABLE source_insight TYPE option<string>;
DEFINE FIELD IF NOT EXISTS owner ON TABLE source_embedding TYPE option<string>;

-- Indexes for efficient filtering by owner
DEFINE INDEX IF NOT EXISTS idx_notebook_owner ON TABLE notebook COLUMNS owner;
DEFINE INDEX IF NOT EXISTS idx_source_owner ON TABLE source COLUMNS owner;
DEFINE INDEX IF NOT EXISTS idx_note_owner ON TABLE note COLUMNS owner;
DEFINE INDEX IF NOT EXISTS idx_chat_session_owner ON TABLE chat_session COLUMNS owner;
```

Create `15_down.surrealql` to remove these fields. Register both in [open_notebook/database/async_migrate.py](open_notebook/database/async_migrate.py) by appending to the `up_migrations` and `down_migrations` lists.

### 2.4 Update `fn::text_search` and `fn::vector_search`

Add an optional `$owner` parameter to both SurrealDB functions (in migration 15). Add `WHERE owner = $owner` or `AND owner = $owner` clauses to all sub-queries in each function (source, source_embedding, source_insight, note). The Python callers in [open_notebook/domain/notebook.py](open_notebook/domain/notebook.py) (`text_search()`, `vector_search()`) gain an `owner: Optional[str] = None` parameter that gets passed through.

### 2.5 Update all routers for user scoping

Each data-serving router needs changes in two areas:

- **List/read**: filter by `owner` from `get_current_user()`
- **Create**: set `owner` from current user on new records
- **Update/delete**: verify `owner` matches before allowing mutation

**Files and key changes:**

- [api/routers/notebooks.py](api/routers/notebooks.py): `GET /notebooks` adds `WHERE owner = $owner`; `POST /notebooks` sets `owner` on the `Notebook` instance; `PUT/DELETE` check owner
- [api/routers/sources.py](api/routers/sources.py): `GET /sources` filters by owner; `POST /sources` sets owner; `PUT/DELETE/retry/download` check owner
- [api/routers/notes.py](api/routers/notes.py): Same pattern -- list, create, update, delete
- [api/routers/insights.py](api/routers/insights.py): `GET/DELETE` check owner; `save-as-note` sets owner
- [api/routers/search.py](api/routers/search.py): Pass `owner` to `vector_search()`/`text_search()`; pass it into ask graph config
- [api/routers/chat.py](api/routers/chat.py): Session CRUD scoped by owner; `POST /chat/context` and `POST /chat/execute` validate source/note ownership
- [api/routers/source_chat.py](api/routers/source_chat.py): Verify source ownership before allowing session creation/messages
- [api/routers/podcasts.py](api/routers/podcasts.py): Episode list/create/delete scoped by owner
- [api/routers/context.py](api/routers/context.py): Validate source/note IDs belong to the user

**Backward compatibility**: when `ENABLE_LDAP=false` and no password is set (dev mode), `owner` is `None` and filtering is skipped -- all records visible (same as today). When password auth is used without LDAP, all users share one identity (`__password_`_), so behavior is unchanged.

### 2.6 Frontend: no structural changes needed

The frontend already stores and sends the JWT/password as Bearer token. The backend will enforce scoping server-side. No frontend code changes are required for data isolation.

---

## Phase 3: Code Quality Fixes

### 3.1 Use custom exceptions instead of HTTPException (review 5.1)

**Agent:** `backend-architect`

In [api/routers/auth.py](api/routers/auth.py), replace `raise HTTPException(...)` with:

- `AuthenticationError(...)` for 401 cases (user not found, bind failed, mismatch)
- `ConfigurationError(...)` for 500/config cases (TLS error, server connect, JWT secret missing)
- `InvalidInputError(...)` for 400 cases (LDAP disabled, missing email)

The global handlers in [api/main.py](api/main.py) already map these to the correct HTTP status codes.

In [api/auth.py](api/auth.py), change `create_ldap_jwt()` to raise `ConfigurationError` instead of `ValueError`.

### 3.2 Fix fragile `cn` extraction (review 5.3)

In [api/routers/auth.py](api/routers/auth.py) line ~191:

```python
# BEFORE:
cn = str(entry["cn"])

# AFTER:
cn_value = entry["cn"].value
cn = cn_value[0] if isinstance(cn_value, list) else str(cn_value)
```

### 3.3 Use i18n key `ldapAuthFailed` in auth store (review 5.4)

**Agent:** `frontend-developer`

In [frontend/src/lib/stores/auth-store.ts](frontend/src/lib/stores/auth-store.ts), the `ldapLogin` catch block hardcodes `'LDAP authentication failed'`. This cannot directly use `t.auth.ldapAuthFailed` because the store is not a React component (no hooks). Two options:

- **Option A**: Pass the translated error string from the hook/component level (LoginForm catches the error and sets a translated message)
- **Option B**: Store an error key (`'ldapAuthFailed'`) instead of a message string; the component resolves it via `t.auth[errorKey]`

**Recommend Option A**: In [frontend/src/lib/hooks/use-auth.ts](frontend/src/lib/hooks/use-auth.ts), wrap `ldapLogin()` and override generic errors with `t.auth.ldapAuthFailed`. This follows the existing pattern where the store holds raw error strings and the UI could override them.

### 3.4 Remove `/ldap/toggle` endpoint (review 5.5)

**Agent:** `backend-architect`

Delete the `POST /api/auth/ldap/toggle` endpoint from [api/routers/auth.py](api/routers/auth.py). Its functionality is already covered by `POST /api/auth/ldap/config`. The ephemeral toggle without config validation is a footgun.

### 3.5 Normalize env var name for search filters (review 5.6)

In [api/ldap_config.py](api/ldap_config.py), keep only `LDAP_SEARCH_FILTERS` (matching docs and docker-compose) and remove the `LDAP_SEARCH_FILTER` singular fallback to avoid confusion.

---

## Files Modified Summary

**Backend (Python):**

- `api/auth.py` -- middleware LDAP-only fix, `request.state.user`, `get_current_user` dependency, custom exceptions
- `api/routers/auth.py` -- connection cleanup, timeout, custom exceptions, `cn` fix, remove toggle, fix `auth_enabled`
- `api/ldap_config.py` -- remove `LDAP_SEARCH_FILTER` singular alias
- `api/routers/notebooks.py` -- owner scoping
- `api/routers/sources.py` -- owner scoping
- `api/routers/notes.py` -- owner scoping
- `api/routers/insights.py` -- owner scoping
- `api/routers/search.py` -- owner passthrough
- `api/routers/chat.py` -- owner scoping
- `api/routers/source_chat.py` -- owner scoping
- `api/routers/podcasts.py` -- owner scoping
- `api/routers/context.py` -- owner validation
- `open_notebook/domain/base.py` -- add `owner` field to ObjectModel, update `get_all()`
- `open_notebook/domain/notebook.py` -- `text_search`/`vector_search` owner param
- `open_notebook/database/migrations/15.surrealql` (new) -- owner fields + indexes
- `open_notebook/database/migrations/15_down.surrealql` (new) -- rollback
- `open_notebook/database/async_migrate.py` -- register migration 15
- `docs/5-CONFIGURATION/security.md` -- fix LDAP-only claim

**Frontend (TypeScript):**

- `frontend/src/lib/hooks/use-auth.ts` -- i18n error override for LDAP

