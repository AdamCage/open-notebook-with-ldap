---
name: surrealdb-migrations
description: Create and manage SurrealDB schema migrations for Open Notebook. Covers file naming, SurrealQL patterns for fields/indexes/functions, registration in async_migrate.py, and rollback files. Use when making database schema changes, adding new fields, tables, indexes, or SurrealDB functions.
---

# SurrealDB Migrations

## Migration File Convention

Migrations live in `open_notebook/database/migrations/`. Each migration is a pair:

```
NNN.surrealql         — up migration (applied on startup)
NNN_down.surrealql    — down migration (manual rollback)
```

Where `NNN` is a sequential integer (e.g., `15`, `16`). Check existing files to determine the next number.

## Registration

After creating migration files, register them in `open_notebook/database/async_migrate.py`:

```python
up_migrations = [
    # ... existing ...
    ("15", "open_notebook/database/migrations/15.surrealql"),
    ("16", "open_notebook/database/migrations/16.surrealql"),  # your new one
]

down_migrations = [
    # ... existing ...
    ("15", "open_notebook/database/migrations/15_down.surrealql"),
    ("16", "open_notebook/database/migrations/16_down.surrealql"),
]
```

Migrations run automatically on API startup via `AsyncMigrationManager`.

## Common SurrealQL Patterns

### Add a field

```sql
DEFINE FIELD IF NOT EXISTS my_field ON TABLE my_table TYPE option<string>;
```

### Add an index

```sql
DEFINE INDEX IF NOT EXISTS idx_my_table_my_field ON TABLE my_table COLUMNS my_field;
```

### Define or redefine a function

```sql
DEFINE FUNCTION IF NOT EXISTS fn::my_function($param: string) {
    RETURN SELECT * FROM my_table WHERE field = $param;
};
```

### Rollback pattern

```sql
-- NNN_down.surrealql
REMOVE FIELD my_field ON TABLE my_table;
REMOVE INDEX idx_my_table_my_field ON TABLE my_table;
```

## Owner Field Pattern (Migration 15)

When adding owner-scoped data isolation to a new table:

```sql
DEFINE FIELD IF NOT EXISTS owner ON TABLE new_table TYPE option<string>;
DEFINE INDEX IF NOT EXISTS idx_new_table_owner ON TABLE new_table COLUMNS owner;
```

Update search functions if they query the new table to accept `$owner` and filter with `($owner IS NONE OR owner = $owner)`.

## Testing

1. Start the API: migrations apply automatically
2. Check logs for "Migration NNN applied successfully"
3. Verify via SurrealDB admin: `INFO FOR TABLE my_table;`
4. Test rollback manually: run `_down.surrealql` content via SurrealDB CLI
