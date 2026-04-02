---
name: Write review v2
overview: Write review_v2.md documenting the re-review of LDAP implementation after all three phases of fixes, with a detailed compliance matrix and remaining gaps analysis.
todos:
  - id: write-review-v2
    content: Write review_v2.md with all findings from the re-review
    status: completed
isProject: false
---

# Review V2: LDAP Module After Fixes

## Scope

Write [review_v2.md](review_v2.md) in the project root with a comprehensive re-review covering all three fix phases and their correctness.

## Key findings

### Phase 1: Critical Security Fixes -- ALL RESOLVED

- **LDAP-only mode**: Fixed. `_is_auth_required()` in [api/auth.py](api/auth.py) line 129-134 now checks both `self.password` and `get_ldap_settings().enable_ldap`. Middleware enforces JWT when only LDAP is enabled. `check_api_password` also updated (line 197). Docs corrected in [security.md](docs/5-CONFIGURATION/security.md).
- **Connection cleanup**: Fixed. `try/finally` at lines 240-246 of [api/routers/auth.py](api/routers/auth.py) unbinds both connections.
- **Connection timeout**: Fixed. `connect_timeout=15` on `Server()` at line 117.

### Phase 2: Per-User Data Isolation -- MOSTLY DONE, 4 GAPS

**What works:**

- `ObjectModel.owner` field in [base.py](open_notebook/domain/base.py)
- `get_all(..., owner=)` filter
- Migration 15 (fields, indexes, search functions with `$owner`)
- Registered in async_migrate.py + down migration exists
- `text_search` / `vector_search` accept `owner` parameter
- Routers: notebooks, sources, notes, chat, source_chat, insights, context -- all use `get_current_user` + `get_owner_id`

**Remaining gaps:**

1. **Podcasts router** (`api/routers/podcasts.py`): imports `get_owner_id` but **never uses it**. List/get/delete/retry/audio endpoints have no per-user filtering. Users can see/manage all podcasts.
2. **Search /ask endpoints** (`api/routers/search.py`): `POST /search` passes `owner`, but `/search/ask` and `/search/ask/simple` do **not** inject `get_current_user` and do **not** pass `owner` to the ask graph. Results may include other users' data.
3. **Cross-resource linking without ownership checks**:
  - `notes.create_note`: when `notebook_id` is provided, loads notebook but does not verify `notebook.owner == get_owner_id(user)` before linking.
  - `sources.create_source`: validates notebook existence for `notebooks` list but does not verify user owns those notebooks.
4. `**ObjectModel.get(id)` does not enforce owner**: Isolation relies on routers checking ownership after fetch. If a router misses the check, data leaks.

### Phase 3: Code Quality -- ALL RESOLVED (1 minor note)

- **Custom exceptions**: All `HTTPException` in LDAP code replaced with `AuthenticationError`, `ConfigurationError`, `InvalidInputError`. `create_ldap_jwt` raises `ConfigurationError`.
- **CN extraction**: Fixed -- `entry["cn"].value` with list handling.
- **Toggle endpoint removed**: Confirmed gone.
- **Env var normalized**: Only `LDAP_SEARCH_FILTERS` used.
- **i18n fix (partial)**: Hook overrides store error with `t.auth.ldapAuthFailed`, but **only** when the store error is exactly `'LDAP authentication failed'`. API-specific error messages from the backend (e.g. "User not found in the LDAP server") bypass the i18n replacement and show in English.

## Document structure

```
1. Summary / Status Delta from review_v1
2. Phase 1 verification (critical security)
3. Phase 2 verification (data isolation) + remaining gaps
4. Phase 3 verification (code quality)
5. Original ТЗ compliance matrix (updated)
6. Remaining recommendations
```

