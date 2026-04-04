---
name: Fix invisible worker errors
overview: Source processing commands fail silently because all exceptions are logged at DEBUG level. The fix surfaces these errors and addresses a potential LangGraph conditional edge issue with empty transformations.
todos:
  - id: surface-errors
    content: Change logger.debug to logger.warning for transient errors in both process_source_command and run_transformation_command. Change retry_log_level from 'debug' to 'warning'.
    status: completed
  - id: diagnostic-logging
    content: Add INFO-level logs before/after Source.get(), source.save(), and source_graph.ainvoke() in process_source_command.
    status: completed
  - id: langgraph-fix
    content: Fix trigger_transformations to return END when no transformations, and update add_conditional_edges path_map to include END.
    status: completed
  - id: stop-on-fix
    content: Add NotFoundError and InvalidInputError to stop_on list in both process_source and run_transformation retry configs.
    status: completed
isProject: false
---

# Fix Invisible Worker Errors and Source Processing Failures

## Problem

The `surreal-commands-worker` picks up `process_source` commands but they all fail silently. The terminal shows "Starting source processing" and "Loaded N transformations" but never "Updated source..." or "Successfully processed source". The same source IDs retry with exponential backoff indefinitely.

The root cause of the *invisibility* is in [commands/source_commands.py](commands/source_commands.py):

```python
# Line ~155: ALL non-ValueError exceptions logged at DEBUG (invisible)
except Exception as e:
    logger.debug(f"Transient error processing source {input_data.source_id}: {e}")
    raise
```

Combined with the retry decorator config:
```python
"retry_log_level": "debug",  # Also invisible
```

This means the actual exception message is never shown at the default INFO log level.

## Fixes

### 1. Surface transient errors at WARNING level

In [commands/source_commands.py](commands/source_commands.py), change `logger.debug` to `logger.warning` in both `process_source_command` and `run_transformation_command` exception handlers. Also change `retry_log_level` from `"debug"` to `"warning"`.

This immediately reveals the actual exception (the most critical fix).

### 2. Add diagnostic logging between major steps

In [commands/source_commands.py](commands/source_commands.py), add INFO-level logging for each substep between "Loaded N transformations" and "Updated source...", specifically:
- Before/after `Source.get()`
- Before/after `source.save()` (the command-reference update)
- Before/after `source_graph.ainvoke()`

This narrows down the exact failure point even further.

### 3. Fix LangGraph empty Send edge case

In [open_notebook/graphs/source.py](open_notebook/graphs/source.py), the graph currently has:

```python
workflow.add_conditional_edges(
    "save_source", trigger_transformations, ["transform_content"]
)
workflow.add_edge("transform_content", END)
```

When `trigger_transformations` returns `[]` (no transformations), there is no explicit path from `save_source` to `END`. In LangGraph `1.0.10rc1`, this may cause the graph to hang or raise an error.

Fix: add `END` as a valid target in the path map and modify `trigger_transformations` to return `[END]` when no transformations are needed:

```python
def trigger_transformations(state, config):
    if len(state["apply_transformations"]) == 0:
        return END
    ...
    return [Send("transform_content", {...}) for t in to_apply]

workflow.add_conditional_edges(
    "save_source", trigger_transformations, ["transform_content", END]
)
```

### 4. Improve `stop_on` error classification

In [commands/source_commands.py](commands/source_commands.py), add `NotFoundError` and `InvalidInputError` to the `stop_on` list. A missing source record or invalid input will not resolve on retry, so retrying 15 times just wastes resources and keeps the source stuck in "Processing..." longer.

```python
from open_notebook.exceptions import ConfigurationError, NotFoundError, InvalidInputError

@command("process_source", app="open_notebook", retry={
    ...
    "stop_on": [ValueError, ConfigurationError, NotFoundError, InvalidInputError],
})
```

### 5. Same fixes for `run_transformation_command`

Apply identical logging and `stop_on` improvements to the `run_transformation_command` handler in the same file.

## Files to modify

- [commands/source_commands.py](commands/source_commands.py) -- logging level, stop_on, diagnostic logs
- [open_notebook/graphs/source.py](open_notebook/graphs/source.py) -- LangGraph conditional edge fix

## Expected outcome

After these changes, re-running the worker will show the **actual exception message** at WARNING level, making it possible to diagnose and fix the underlying root cause (likely a DB transaction conflict, connection issue, or content extraction error). The LangGraph fix ensures the no-transformations case completes properly.
