---
name: User Auth and RBAC
overview: Implement a full user management system with local registration (with admin approval), LDAP auto-registration, role-based access control (admin/user), admin panel for system configuration, and per-user data isolation -- all without breaking backward compatibility with the existing password-only and no-auth modes.
todos:
  - id: phase1-db
    content: "Phase 1: Create migration 16 (app_user table) + AppUser domain model with bcrypt"
    status: completed
  - id: phase2-env
    content: "Phase 2: Add AUTH_MODE/ADMIN_USERNAME/ADMIN_PASSWORD to .env, create auth_config.py, update lifespan bootstrap"
    status: completed
  - id: phase3-auth-api
    content: "Phase 3a: Update auth middleware + JWT to include role; add /auth/register, /auth/login, /auth/me endpoints"
    status: completed
  - id: phase3-ldap-update
    content: "Phase 3b: Update LDAP login to auto-register AppUser on first login"
    status: completed
  - id: phase3-users-api
    content: "Phase 3c: Create /users/* admin endpoints (list, approve, deactivate, role management)"
    status: completed
  - id: phase3-guards
    content: "Phase 3d: Add role-based guards to admin-only endpoints (credentials, models, settings, advanced)"
    status: completed
  - id: phase4-auth-frontend
    content: "Phase 4a: Update auth store, LoginForm for local mode, create register + pending pages"
    status: completed
  - id: phase4-admin-frontend
    content: "Phase 4b: Create admin user management page, update sidebar/nav for role-based visibility"
    status: completed
  - id: phase4-i18n
    content: "Phase 4c: Add i18n keys for all new auth/admin UI strings"
    status: completed
  - id: phase5-test
    content: "Phase 5: Test all auth flows (local register+approve, LDAP auto-register, role guards, backward compat)"
    status: completed
isProject: false
---

# User Authentication and Role-Based Access Control

## Architecture Overview

```mermaid
flowchart TD
    subgraph authModes [AUTH_MODE in .env]
        none["none (default) -- no auth, current behavior"]
        password["password -- shared password, no isolation"]
        local["local -- local user DB + registration"]
        ldap["ldap -- LDAP + auto-registration"]
    end

    subgraph roles [Roles]
        superAdmin["super_admin (via .env ADMIN_USERNAME)"]
        admin["admin (promoted by super_admin)"]
        user["user (default role)"]
    end

    local --> RegisterEndpoint
    RegisterEndpoint --> PendingApproval["status: pending"]
    PendingApproval --> AdminApproves --> ActiveUser["status: active"]

    ldap --> LDAPLogin
    LDAPLogin --> AutoRegister["auto-create user, status: active"]

    superAdmin --> ManageUsers["view users, grant/revoke admin"]
    admin --> ManageConfig["models, credentials, settings, transformations"]
    admin -. "CANNOT" .-> ViewOtherNotebooks["view other users' notebooks"]
    user --> OwnNotebooks["create/manage own notebooks only"]
end
```

## Phase 1: Database -- User Table and Migration

### Migration 16 (`open_notebook/database/migrations/16.surrealql`)

```sql
DEFINE TABLE IF NOT EXISTS app_user SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS username ON TABLE app_user TYPE string;
DEFINE FIELD IF NOT EXISTS email ON TABLE app_user TYPE string;
DEFINE FIELD IF NOT EXISTS display_name ON TABLE app_user TYPE option<string>;
DEFINE FIELD IF NOT EXISTS password_hash ON TABLE app_user TYPE option<string>;
DEFINE FIELD IF NOT EXISTS role ON TABLE app_user TYPE string DEFAULT 'user';
  -- values: 'super_admin', 'admin', 'user'
DEFINE FIELD IF NOT EXISTS status ON TABLE app_user TYPE string DEFAULT 'pending';
  -- values: 'pending', 'active', 'deactivated'
DEFINE FIELD IF NOT EXISTS auth_provider ON TABLE app_user TYPE string DEFAULT 'local';
  -- values: 'local', 'ldap'
DEFINE FIELD IF NOT EXISTS created ON TABLE app_user TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS updated ON TABLE app_user TYPE option<datetime>;
DEFINE FIELD IF NOT EXISTS last_login ON TABLE app_user TYPE option<datetime>;

DEFINE INDEX IF NOT EXISTS idx_app_user_username ON TABLE app_user COLUMNS username UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_app_user_email ON TABLE app_user COLUMNS email UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_app_user_status ON TABLE app_user COLUMNS status;
```

Register migration 16 (and 16_down) in [open_notebook/database/async_migrate.py](open_notebook/database/async_migrate.py) `AsyncMigrationManager.__init__`.

### Domain Model (`open_notebook/domain/app_user.py`)

New `AppUser(ObjectModel)` with `table_name = "app_user"`. Key methods:
- `get_by_username(username)` -- class method, query by username
- `get_by_email(email)` -- class method
- `verify_password(plain)` -- check bcrypt hash
- `set_password(plain)` -- hash and store
- `is_active` property -- `status == "active"`
- `is_admin` property -- `role in ("admin", "super_admin")`

Password hashing: use `bcrypt` (add to `pyproject.toml`). Only populated for `auth_provider = "local"`; LDAP users have `password_hash = None`.

## Phase 2: Environment Configuration

### New `.env` variables

```
AUTH_MODE=none
  # none     -- no auth (default, backward compat)
  # password -- shared password (OPEN_NOTEBOOK_PASSWORD), no isolation
  # local    -- local user DB with registration + admin approval
  # ldap     -- LDAP auth with auto-registration on first login

ADMIN_USERNAME=admin
  # Super-admin username. On startup:
  #   - local mode: if user doesn't exist, auto-create with ADMIN_PASSWORD
  #   - ldap mode: on first LDAP login of this username, auto-promote to super_admin
ADMIN_PASSWORD=changeme
  # Initial password for super-admin in local mode (only used on first creation)
```

### Validation in startup (`api/main.py` lifespan)

- `AUTH_MODE=local` or `AUTH_MODE=ldap` -- `OPEN_NOTEBOOK_PASSWORD` is **ignored** (log warning if set)
- `AUTH_MODE=local` -- require `ADMIN_USERNAME` + `ADMIN_PASSWORD`; auto-create super_admin if not in DB
- `AUTH_MODE=ldap` -- require `ENABLE_LDAP=true` + existing LDAP config; store `ADMIN_USERNAME` for later promotion
- `AUTH_MODE=password` -- existing behavior unchanged
- `AUTH_MODE=none` -- existing behavior unchanged

## Phase 3: Backend API

### Auth config module (`api/auth_config.py`)

New module to centralize auth mode resolution:
- `get_auth_mode() -> Literal["none", "password", "local", "ldap"]`
- `is_multi_user() -> bool` -- True for `local` and `ldap` modes
- `require_admin(user)` -- raise 403 if not admin
- `require_super_admin(user)` -- raise 403 if not super_admin
- `require_active(user)` -- raise 403 if status != active

### Updated middleware ([api/auth.py](api/auth.py))

`PasswordAuthMiddleware.dispatch` behavior per mode:
- **none**: `request.state.user = None` (unchanged)
- **password**: check `OPEN_NOTEBOOK_PASSWORD` (unchanged)
- **local**: decode JWT from Bearer, lookup `AppUser`, verify active, set `request.state.user = {"sub": username, "role": role, "type": "local", ...}`
- **ldap**: decode JWT (existing logic), but also check AppUser record is active

New helper: `create_user_jwt(user: AppUser) -> str` -- same HS256 structure as LDAP JWT but with `type: "local"`, `role` claim added.

Update `_extract_user_identity` to include `role` from JWT claims.

### Registration endpoint (`api/routers/auth.py`)

New endpoints (only active when `AUTH_MODE=local`):

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | Public | Register new user (username, email, password, display_name). Creates AppUser with `status=pending`. Returns 201. |
| POST | `/auth/login` | Public | Login with username + password. Returns JWT if user is active; returns 403 with message if pending/deactivated. |
| GET | `/auth/me` | User | Return current user profile (username, email, role, status). |
| PUT | `/auth/me` | User | Update own profile (display_name, email) -- local mode only. |
| PUT | `/auth/me/password` | User | Change own password -- local mode only. |

Updated endpoints for LDAP (`AUTH_MODE=ldap`):
- `POST /auth/ldap`: existing flow + **after successful LDAP bind**, upsert `AppUser` record (create if first login, update `last_login` if exists). If `username == ADMIN_USERNAME`, set `role=super_admin`.

### User management endpoints (`api/routers/users.py`)

New router, requires admin role:

| Method | Path | Role | Description |
|--------|------|------|-------------|
| GET | `/users` | admin | List all users (username, email, role, status, last_login). No notebook data exposed. |
| GET | `/users/{user_id}` | admin | Get single user details. |
| PUT | `/users/{user_id}/approve` | admin | Set status from `pending` to `active`. |
| PUT | `/users/{user_id}/deactivate` | admin | Set status to `deactivated`. |
| PUT | `/users/{user_id}/activate` | admin | Re-activate a deactivated user. |
| PUT | `/users/{user_id}/role` | super_admin | Set role to `admin` or `user`. Only super_admin can change roles. |

### Protected endpoints -- role-based guards

Admin-only endpoints (return 403 for regular users):
- `GET/POST /credentials/*` -- all credential management
- `GET/POST /models/*` -- model configuration
- `GET/PUT /settings` -- app settings
- `GET/POST /advanced/*` -- system info, rebuild embeddings
- `GET/POST /auth/ldap/config` -- LDAP configuration
- `POST /transformations` -- creating/editing transformations (reading remains available to all)

User endpoints (scoped by `owner_id`):
- All notebook/source/note/chat/podcast/search endpoints -- already scoped, no changes needed beyond ensuring `owner_id` comes from JWT `sub` claim

## Phase 4: Frontend

### Auth store updates ([frontend/src/lib/stores/auth-store.ts](frontend/src/lib/stores/auth-store.ts))

Add to store state:
- `user: { username, email, displayName, role, status } | null`
- `isAdmin: boolean` (derived from role)
- `authMode: "none" | "password" | "local" | "ldap"`

Update `checkAuthRequired` to also fetch `auth_mode` from `/api/auth/status`.

Add actions:
- `register(username, email, password, displayName)` -- POST `/auth/register`
- `localLogin(username, password)` -- POST `/auth/login`
- `fetchProfile()` -- GET `/auth/me` (called after login, stores user info)

### Login page updates ([frontend/src/components/auth/LoginForm.tsx](frontend/src/components/auth/LoginForm.tsx))

Based on `authMode` from backend:
- **none**: auto-redirect (unchanged)
- **password**: single password field (unchanged)
- **local**: username + password + "Sign In" button + link to registration form
- **ldap**: username + password + "Sign In with LDAP" (unchanged)

### Registration page (`frontend/src/app/(auth)/register/page.tsx`)

New page (only accessible when `AUTH_MODE=local`):
- Fields: username, email, password, confirm password, display name
- On submit: POST `/auth/register`
- On success: redirect to a "pending approval" page

### Pending approval page (`frontend/src/app/(auth)/pending/page.tsx`)

Friendly page shown after registration or when a pending user tries to login:
- Message: "Your account is awaiting administrator approval"
- Link to retry login

### Admin panel

#### Navigation ([frontend/src/components/layout/AppSidebar.tsx](frontend/src/components/layout/AppSidebar.tsx))

Conditionally show "Manage" section based on `isAdmin` from auth store:
- **Admin users**: see Models, Transformations, Settings, Advanced, **Users** (new)
- **Regular users**: only see Notebooks, Search (hide entire Manage section)

#### User management page (`frontend/src/app/(dashboard)/admin/users/page.tsx`)

New admin page:
- Table of users: username, email, role, status, last login
- Actions per user:
  - Approve (pending -> active)
  - Deactivate / Activate
  - Grant Admin / Revoke Admin (super_admin only)
- Filter by status (pending, active, deactivated)
- No access to user notebooks/data

### i18n updates

Add keys to all locale files (`en-US`, etc.):
- `auth.registerTitle`, `auth.registerDesc`, `auth.registerButton`
- `auth.pendingTitle`, `auth.pendingDesc`
- `auth.localLoginDesc`
- `admin.users`, `admin.approveUser`, `admin.deactivateUser`, `admin.grantAdmin`, `admin.revokeAdmin`
- `errors.accountPending`, `errors.accountDeactivated`
- `navigation.users`

## Phase 5: Security Considerations

- **Password hashing**: bcrypt with default rounds (12)
- **JWT expiry**: 24 hours (same as LDAP), consider adding refresh token later
- **Rate limiting**: Not in scope for initial implementation, but add TODO for brute-force protection on `/auth/login` and `/auth/register`
- **CORS**: unchanged (already configured)
- **Role checks on server**: ALL permission checks enforced on API side; frontend hides UI elements but server is the authority
- **Super-admin protection**: super_admin cannot be deactivated or demoted via API; only `.env` change

## Things NOT in this plan (future work)

- Refresh tokens / session management
- Rate limiting on login/register
- Email notifications (admin notified of new registrations)
- Password complexity requirements (can be added later via Pydantic validators)
- Audit log for admin actions
- Transformations per-user (currently global, stays global, only admins create)

## Affected Files Summary

**New files:**
- `open_notebook/domain/app_user.py`
- `open_notebook/database/migrations/16.surrealql` + `16_down.surrealql`
- `api/auth_config.py`
- `api/routers/users.py`
- `frontend/src/app/(auth)/register/page.tsx`
- `frontend/src/app/(auth)/pending/page.tsx`
- `frontend/src/app/(dashboard)/admin/users/page.tsx` + components
- `frontend/src/lib/api/users.ts`
- `frontend/src/lib/hooks/use-users.ts`

**Modified files:**
- [api/auth.py](api/auth.py) -- JWT with role, updated middleware, local login
- [api/routers/auth.py](api/routers/auth.py) -- register, login, me, LDAP auto-register
- [api/main.py](api/main.py) -- lifespan: super-admin bootstrap, auth mode validation
- [api/ldap_config.py](api/ldap_config.py) -- minor: expose auth_mode in status
- [open_notebook/database/async_migrate.py](open_notebook/database/async_migrate.py) -- register migration 16
- [frontend/src/lib/stores/auth-store.ts](frontend/src/lib/stores/auth-store.ts) -- user object, role, auth mode
- [frontend/src/lib/hooks/use-auth.ts](frontend/src/lib/hooks/use-auth.ts) -- register, local login
- [frontend/src/components/auth/LoginForm.tsx](frontend/src/components/auth/LoginForm.tsx) -- local mode UI
- [frontend/src/components/layout/AppSidebar.tsx](frontend/src/components/layout/AppSidebar.tsx) -- role-based nav
- [frontend/src/components/common/CommandPalette.tsx](frontend/src/components/common/CommandPalette.tsx) -- role filter
- [frontend/src/lib/locales/en-US/index.ts](frontend/src/lib/locales/en-US/index.ts) -- new keys
- [.env](.env) -- new AUTH_MODE, ADMIN_USERNAME, ADMIN_PASSWORD
- All admin-only routers (credentials, models, settings, advanced) -- add role guard
