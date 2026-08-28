from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import get_principal, get_scoped_session
from packages.contracts.identity import AuthenticatedPrincipal
from packages.contracts.memory import MemoryCreateRequest, MemorySearchRequest, MemoryView
from packages.memory.service import memory_service

router = APIRouter(prefix="/api/v1/memories", tags=["Memory"])


@router.post("", operation_id="memories_create", response_model=MemoryView, status_code=201)
async def create_memory(
    body: MemoryCreateRequest,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    db: AsyncSession = Depends(get_scoped_session),
) -> MemoryView:
    try:
        value = await memory_service.create(db, principal, body)
        await db.flush()
        return MemoryView.model_validate(value)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/search", operation_id="memories_search", response_model=list[MemoryView])
async def search_memories(
    body: MemorySearchRequest,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    db: AsyncSession = Depends(get_scoped_session),
) -> list[MemoryView]:
    values = await memory_service.search(db, principal, body)
    return [MemoryView.model_validate(value) for value in values]


@router.get("/{memory_id}", operation_id="memories_get", response_model=MemoryView)
async def get_memory(
    memory_id: UUID,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    db: AsyncSession = Depends(get_scoped_session),
) -> MemoryView:
    try:
        return MemoryView.model_validate(await memory_service.get(db, principal, memory_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{memory_id}", operation_id="memories_forget", status_code=status.HTTP_204_NO_CONTENT)
async def forget_memory(
    memory_id: UUID,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    db: AsyncSession = Depends(get_scoped_session),
) -> Response:
    try:
        await memory_service.forget(db, principal, memory_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
