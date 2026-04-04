---
name: Fix Source Processing Issues
overview: "Fix two issues: (1) documents stuck in \"Processing...\" because the command worker is not running in the user's dev setup; (2) newly created sources don't appear in the UI until page refresh because the create mutation doesn't invalidate the infinite scroll query."
todos:
  - id: fix-docs-worker
    content: Add 'Start Background Worker' step to docs/1-INSTALLATION/from-source.md between API and Frontend steps
    status: completed
  - id: fix-source-invalidation
    content: Add sourcesInfinite invalidation to useCreateSource and useUploadSource onSuccess in use-sources.ts
    status: completed
isProject: false
---

# Fix Source Processing and UI Refresh Issues

## Issue 1: Documents stuck in "Processing..."

### Root cause

Open Notebook runs **four** processes in production (see [supervisord.conf](supervisord.conf)):

1. `surrealdb` -- database
2. `api` -- FastAPI server (`uvicorn`)
3. **`worker`** -- `surreal-commands-worker --import-modules commands`
4. `frontend` -- Next.js

The **command worker** is the process that picks up async jobs (source processing, embedding, podcasts) from the SurrealDB job queue and executes them. Without it, commands are submitted but never run.

The API terminal logs confirm this: there are `Submitted command job: command:... for open_notebook.process_source` entries but zero `Starting source processing` entries -- the worker never picks them up.

The user is running only 3 terminals: SurrealDB (terminal 3), API (terminal 4), and frontend (terminal 5). **The worker is missing.**

### Fix

This is a documentation/developer-experience issue, not a code bug. The [from-source.md](docs/1-INSTALLATION/from-source.md) installation guide lists only 3 steps (database, API, frontend) but omits the worker. Add a new step:

In [docs/1-INSTALLATION/from-source.md](docs/1-INSTALLATION/from-source.md), between "Step 5: Start API" and "Step 6: Start Frontend", add:

```
### 6. Start Background Worker

# Terminal 3
make worker
# or: uv run --env-file .env surreal-commands-worker --import-modules commands
```

And renumber subsequent steps (Frontend becomes 7, Access becomes 8, Configure becomes 9).

The user should start the worker now with `make worker` in a new terminal.

---

## Issue 2: Newly added sources don't appear until page refresh

### Root cause

In [frontend/src/lib/hooks/use-sources.ts](frontend/src/lib/hooks/use-sources.ts), the `useCreateSource` mutation's `onSuccess` invalidates:

- `QUERY_KEYS.sources(notebookId)` = `['sources', notebookId]`
- `QUERY_KEYS.sources()` = `['sources', undefined]`

But the notebook detail page uses `useNotebookSources` which queries with:

- `QUERY_KEYS.sourcesInfinite(notebookId)` = `['sources', 'infinite', notebookId]`

TanStack Query's prefix matching means `['sources', undefined]` does NOT match `['sources', 'infinite', notebookId]` (the second element `undefined` != `'infinite'`). So the infinite scroll query is never invalidated after source creation.

### Fix

In `useCreateSource`'s `onSuccess` callback (line ~96 of [frontend/src/lib/hooks/use-sources.ts](frontend/src/lib/hooks/use-sources.ts)), add invalidation of the `sourcesInfinite` query for each affected notebook:

```typescript
// After the existing notebook-specific invalidations (line ~104), add:
variables.notebooks.forEach(notebookId => {
  queryClient.invalidateQueries({
    queryKey: QUERY_KEYS.sourcesInfinite(notebookId),
    refetchType: 'active'
  })
})
```

And the same for the `notebook_id` branch. Also do the same in `useUploadSource` (line ~203) which has the same issue.

This is a pre-existing upstream bug not caused by our auth changes, but it affects the user experience.
