---
name: api-endpoint-creation
description: Create new FastAPI endpoints following Open Notebook project patterns. Covers router structure, Pydantic request/response models, owner scoping with get_current_user and get_owner_id, error handling with custom exceptions, service layer, and registration in main.py. Use when adding new API routes, CRUD operations, or data endpoints.
---

# API Endpoint Creation

## Step-by-Step

1. **Define Pydantic models** in `api/models.py`
2. **Create router** in `api/routers/feature.py`
3. **Create service** (optional) in `api/feature_service.py`
4. **Register router** in `api/main.py`
5. **Test** at http://localhost:5055/docs

## Router Template

```python
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from api.auth import get_current_user, get_owner_id
from api.models import MyCreateRequest, MyResponse
from open_notebook.domain.notebook import MyModel

router = APIRouter()


@router.get("/mymodels", response_model=List[MyResponse])
async def list_items(
    user: Optional[dict] = Depends(get_current_user),
):
    try:
        owner_id = get_owner_id(user)
        items = await MyModel.get_all(order_by="updated desc", owner=owner_id)
        return [MyResponse(...) for item in items]
    except Exception as e:
        logger.error(f"Error listing items: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mymodels", response_model=MyResponse)
async def create_item(
    data: MyCreateRequest,
    user: Optional[dict] = Depends(get_current_user),
):
    try:
        owner_id = get_owner_id(user)
        item = MyModel(name=data.name, owner=owner_id)
        await item.save()
        return MyResponse(id=item.id, ...)
    except Exception as e:
        logger.error(f"Error creating item: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mymodels/{item_id}", response_model=MyResponse)
async def get_item(
    item_id: str,
    user: Optional[dict] = Depends(get_current_user),
):
    try:
        item = await MyModel.get(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Not found")
        owner_id = get_owner_id(user)
        if owner_id and item.owner != owner_id:
            raise HTTPException(status_code=404, detail="Not found")
        return MyResponse(id=item.id, ...)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching item: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

## Owner Scoping Checklist

Every data endpoint MUST:

- [ ] Inject `user: Optional[dict] = Depends(get_current_user)`
- [ ] Compute `owner_id = get_owner_id(user)`
- [ ] **List**: pass `owner=owner_id` to `get_all()`
- [ ] **Create**: set `owner=owner_id` on the new record
- [ ] **Get/Update/Delete**: check `owner_id and item.owner != owner_id` → 404
- [ ] **Cross-resource links**: verify target notebook/source owner matches

## Registering the Router

In `api/main.py`:

```python
from api.routers import myfeature
app.include_router(myfeature.router, prefix="/api", tags=["myfeature"])
```

## Error Handling

Use custom exceptions from `open_notebook.exceptions`:

| Exception | HTTP Code | When |
|-----------|-----------|------|
| `InvalidInputError` | 400 | Bad request data |
| `AuthenticationError` | 401 | Auth failure |
| `NotFoundError` | 404 | Record not found |
| `ConfigurationError` | 500 | Server misconfiguration |
| `DatabaseOperationError` | 500 | DB query failure |

Global handlers in `api/main.py` auto-map these to HTTP responses.

## Async Job Pattern

For long-running operations, submit to the job queue:

```python
from surreal_commands import submit_command

command_id = submit_command("open_notebook", "my_command", args_dict)
```

Return immediately with `command_id`; client polls `/commands/{id}` for status.
