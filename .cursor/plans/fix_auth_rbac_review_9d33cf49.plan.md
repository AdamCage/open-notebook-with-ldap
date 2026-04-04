---
name: Fix Auth RBAC Review
overview: Address all 22 issues from the code review (3 critical, 7 major, 12 minor) organized by priority and file proximity to minimize churn.
todos:
  - id: p0-critical
    content: "P0: Fix 3 critical issues (unsafe fallback identity, middleware DB status check, transformation PUT guard)"
    status: completed
  - id: p1-major
    content: "P1: Fix 7 major issues (self-deactivation guard, JWT secret separation, transform execute guard, admin route guard, CommandPalette users, security docs, localStorage doc)"
    status: completed
  - id: p2-cleanup
    content: "P2: Fix 12 minor issues (unused imports, validators, deprecated datetime, exception narrowing, TS types, sidebar cast, admin error handling, status param validation, LDAP mode check)"
    status: completed
isProject: false
---

# Fix Auth RBAC Review Issues

## P0: Critical Fixes (Must fix before merge)

### 3.1 -- Unsafe fallback in `_extract_user_identity` ([api/auth.py](api/auth.py))

The `except Exception` block returns `{"role": "admin"}`. Replace with a raise or non-admin identity:

```python
except Exception:
    return {"sub": "__anonymous__", "type": "unknown", "role": "user"}
```

### 3.2 -- No DB-level status check for JWT holders ([api/auth.py](api/auth.py))

In the middleware `dispatch()` for `local`/`ldap` modes, after decoding the JWT, add an async DB lookup to verify the user is still active. Use a simple in-memory TTL cache (60s) to avoid per-request DB hits:

```python
# In PasswordAuthMiddleware, after verify_jwt(credentials):
from open_notebook.domain.app_user import AppUser

db_user = await AppUser.get_by_username(payload.get("sub"))
if not db_user or not db_user.is_active:
    return JSONResponse(status_code=401, content={"detail": "Account deactivated or not found"}, ...)
```

Add a simple dict-based cache `_user_status_cache: dict[str, tuple[float, bool]]` with 60s TTL at the module level.

### 3.11 -- `PUT /transformations/{id}` missing admin guard ([api/routers/transformations.py](api/routers/transformations.py))

Find the `@router.put("/transformations/{transformation_id}")` endpoint and add `dependencies=[Depends(admin_guard)]`.

---

## P1: Major Fixes (Before production)

### 2.2 -- Document `admin_guard` no-op in none/password modes

Add clear comments in [api/auth_config.py](api/auth_config.py) `admin_guard()` and in [.env](.env) warning that `none`/`password` modes disable all RBAC.

### 3.3 -- Separate JWT secret from encryption key ([api/auth.py](api/auth.py))

Update `get_jwt_secret()` to check a new `JWT_SECRET` env var first, then fall back to existing keys. Add `JWT_SECRET` documentation to [.env](.env).

### 3.9 -- Self-deactivation guard ([api/routers/users.py](api/routers/users.py))

In `deactivate_user()`, compare `user_id` to the current user's record ID. Reject if they match.

### 3.12 -- `POST /transformations/execute` missing guard ([api/routers/transformations.py](api/routers/transformations.py))

Add `dependencies=[Depends(admin_guard)]` to the execute endpoint.

### 4.4 -- Token in localStorage

This is a known SPA pattern trade-off. Add a code comment in [frontend/src/lib/stores/auth-store.ts](frontend/src/lib/stores/auth-store.ts) documenting the risk and CSP recommendation.

### 4.11 -- No frontend route guard on admin page ([frontend/src/app/(dashboard)/admin/users/page.tsx](frontend/src/app/(dashboard)/admin/users/page.tsx))

Add an `isAdmin` check at the top of the component. If not admin (and `authMode` is `local`/`ldap`), redirect to `/notebooks` with a toast or show an "Access Denied" card.

### 4.16 -- Missing "Users" in CommandPalette ([frontend/src/components/common/CommandPalette.tsx](frontend/src/components/common/CommandPalette.tsx))

Add a "Users" entry to `getNavigationItems()` inside the admin-gated section. It is currently in `ADMIN_ONLY_PATHS` but not in the items array.

### 4.17 -- English stubs in non-RU/EN locales

Not a code fix -- document that translations are needed. Add a `TODO` comment in the locale files or a note in CONTRIBUTING.md. Actual translation is out of scope for this pass.

---

## P2: Minor Fixes (Quality improvements)

### Unused imports (1.3, 2.1, 3.4)

- [open_notebook/domain/app_user.py](open_notebook/domain/app_user.py): Remove `logger`, `NotFoundError`
- [api/auth_config.py](api/auth_config.py): Remove `Depends`, `Request` (imported but unused in the module itself)
- [api/auth.py](api/auth.py): Remove `logger`

### Missing validators (1.5, 1.7)

- [open_notebook/domain/app_user.py](open_notebook/domain/app_user.py): Add `auth_provider` validator restricting to `("local", "ldap")`
- [api/routers/auth.py](api/routers/auth.py): Enforce minimum 6 char password in `register_user()` and `change_my_password()` (already done in register, verify in change_password)

### Deprecated `datetime.utcnow()` (3.6)

Replace all `datetime.utcnow()` with `datetime.now(timezone.utc)` in [api/routers/auth.py](api/routers/auth.py) (3 occurrences in `local_login`, `_upsert_ldap_user`).

### Broad exception handling (3.5)

In [api/auth.py](api/auth.py) middleware, narrow `except Exception` to `except (jwt.InvalidTokenError, jwt.ExpiredSignatureError, jwt.DecodeError, KeyError)`.

### TypeScript cleanup (4.1, 4.2, 4.7)

- [frontend/src/lib/types/auth.ts](frontend/src/lib/types/auth.ts): Remove unused `AuthState` interface; tighten `role`/`status` to union types
- [frontend/src/lib/stores/auth-store.ts](frontend/src/lib/stores/auth-store.ts): Remove the `as unknown as UserProfile` double assertion in `ldapLogin`

### Sidebar type cast (4.15)

- [frontend/src/components/layout/AppSidebar.tsx](frontend/src/components/layout/AppSidebar.tsx): Use direct `t.navigation.users` if the locale type includes the key (it should after our i18n addition)

### Admin page error handling (4.12)

- [frontend/src/app/(dashboard)/admin/users/page.tsx](frontend/src/app/(dashboard)/admin/users/page.tsx): Handle `isError`/`error` from `useUsers()` -- show error message instead of "No users found"

### `isAdmin: true` for none mode (4.5)

Add a code comment in [frontend/src/lib/stores/auth-store.ts](frontend/src/lib/stores/auth-store.ts) explaining this is intentional for backward compatibility.

### `status` query parameter validation (3.10)

In [api/routers/users.py](api/routers/users.py), validate `status` parameter against allowed values before passing to `get_all_users()`.

### LDAP auth mode check (3.7)

In [api/routers/auth.py](api/routers/auth.py) `ldap_auth()`, also check `get_auth_mode() == "ldap"` in addition to `settings.enable_ldap`.
