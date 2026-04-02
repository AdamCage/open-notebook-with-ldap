---
name: langgraph-workflows
description: Create and modify LangGraph workflow graphs for Open Notebook. Covers StateGraph patterns, async node functions, conditional edges, Send fan-out, configurable dict for context passing, provision_langchain_model, error handling with classify_error, and streaming via astream. Use when building new AI workflows, modifying existing graphs, or debugging graph execution.
---

# LangGraph Workflows

## Existing Graphs

| Graph | File | Purpose |
|-------|------|---------|
| chat | `open_notebook/graphs/chat.py` | Multi-turn conversation with notebook context |
| source_chat | `open_notebook/graphs/source_chat.py` | Source-focused chat with ContextBuilder |
| ask | `open_notebook/graphs/ask.py` | Multi-search strategy → answer synthesis |
| source | `open_notebook/graphs/source.py` | Content ingestion pipeline |
| transformation | `open_notebook/graphs/transformation.py` | Single-node LLM transformation |
| prompt | `open_notebook/graphs/prompt.py` | Generic prompt → completion |

## Creating a New Graph

```python
from langgraph.graph import END, START, StateGraph
from langchain_core.runnables import RunnableConfig
from typing_extensions import TypedDict

from open_notebook.ai.provision import provision_langchain_model
from open_notebook.utils.error_classifier import classify_error
from open_notebook.utils.text_utils import extract_text_content
from open_notebook.utils import clean_thinking_content


class MyState(TypedDict):
    input_text: str
    result: str


async def process_node(state: MyState, config: RunnableConfig) -> dict:
    try:
        model_id = config.get("configurable", {}).get("model_id")
        owner = config.get("configurable", {}).get("owner")
        prompt = f"Process: {state['input_text']}"
        model = await provision_langchain_model(
            prompt, model_id, "tools", max_tokens=2000
        )
        response = await model.ainvoke(prompt)
        content = extract_text_content(response.content)
        return {"result": clean_thinking_content(content)}
    except Exception as e:
        error_class, user_message = classify_error(e)
        raise error_class(user_message) from e


builder = StateGraph(MyState)
builder.add_node("process", process_node)
builder.add_edge(START, "process")
builder.add_edge("process", END)

graph = builder.compile()
```

## Key Patterns

### Passing owner through configurable

```python
# In the router
result = await graph.ainvoke(
    input={"input_text": "..."},
    config={"configurable": {"model_id": "model:xyz", "owner": owner_id}},
)

# In the node
owner = config.get("configurable", {}).get("owner")
results = await vector_search(term, 10, True, True, owner=owner)
```

### Fan-out with Send

```python
from langgraph.types import Send

async def trigger_parallel(state, config):
    return [
        Send("worker_node", {"term": s.term, "instructions": s.instructions})
        for s in state["strategy"].searches
    ]

builder.add_conditional_edges("planner", trigger_parallel, ["worker_node"])
```

### Error handling

Always wrap LLM calls with `classify_error()`:

```python
try:
    response = await model.ainvoke(prompt)
except OpenNotebookError:
    raise
except Exception as e:
    error_class, user_message = classify_error(e)
    raise error_class(user_message) from e
```

### Streaming from a router

```python
async def stream_response(...) -> AsyncGenerator[str, None]:
    async for chunk in graph.astream(input=..., config=..., stream_mode="updates"):
        if "node_name" in chunk:
            yield f"data: {json.dumps(chunk['node_name'])}\n\n"
```

## Quirks

- `provision_langchain_model()` is async; graph nodes must be async
- `clean_thinking_content()` strips `<think>` tags from reasoning models
- Chat graphs use SqliteSaver for checkpoint persistence
- Content-core library (source.py) is synchronous; wrapped in `asyncio.to_thread`
