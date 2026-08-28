from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import get_correlation_id, get_principal, get_scoped_session
from packages.contracts.data import (
    DataDownloadTicket,
    DataGrantCreateRequest,
    DataObjectRegisterRequest,
    DataObjectView,
    DataUploadRequest,
    DataUploadTicket,
)
from packages.contracts.identity import AuthenticatedPrincipal
from packages.data_vault.service import data_vault_service
from packages.data_vault.object_store import ObjectStoreUnavailable

router = APIRouter(prefix="/api/v1/data", tags=["Data vault"])


@router.post("/uploads", operation_id="data_uploads_create", response_model=DataUploadTicket, status_code=201)
async def initiate_upload(
    body: DataUploadRequest,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    correlation_id: UUID = Depends(get_correlation_id),
    db: AsyncSession = Depends(get_scoped_session),
) -> DataUploadTicket:
    try:
        value, ticket = await data_vault_service.initiate_upload(
            db, principal, body, correlation_id
        )
        await db.flush()
        return DataUploadTicket(
            object=DataObjectView.model_validate(value),
            upload_url=ticket.url,
            required_headers=ticket.required_headers,
            expires_in_seconds=ticket.expires_in_seconds,
        )
    except ObjectStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/uploads/{object_id}/complete",
    operation_id="data_uploads_complete",
    response_model=DataObjectView,
)
async def complete_upload(
    object_id: UUID,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    correlation_id: UUID = Depends(get_correlation_id),
    db: AsyncSession = Depends(get_scoped_session),
) -> DataObjectView:
    try:
        value = await data_vault_service.complete_upload(
            db, principal, object_id, correlation_id
        )
        return DataObjectView.model_validate(value)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ObjectStoreUnavailable, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/objects/{object_id}/download",
    operation_id="data_objects_download",
    response_model=DataDownloadTicket,
)
async def authorize_download(
    object_id: UUID,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    correlation_id: UUID = Depends(get_correlation_id),
    db: AsyncSession = Depends(get_scoped_session),
) -> DataDownloadTicket:
    try:
        url = await data_vault_service.download_ticket(
            db, principal, object_id, correlation_id
        )
        return DataDownloadTicket(object_id=object_id, download_url=url, expires_in_seconds=300)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ObjectStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/objects", operation_id="data_objects_register", response_model=DataObjectView, status_code=201)
async def register_object(
    body: DataObjectRegisterRequest,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    correlation_id: UUID = Depends(get_correlation_id),
    db: AsyncSession = Depends(get_scoped_session),
) -> DataObjectView:
    try:
        value = await data_vault_service.register(db, principal, body, correlation_id)
        await db.flush()
        return DataObjectView.model_validate(value)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/objects", operation_id="data_objects_list", response_model=list[DataObjectView])
async def list_objects(
    principal: AuthenticatedPrincipal = Depends(get_principal),
    db: AsyncSession = Depends(get_scoped_session),
) -> list[DataObjectView]:
    values = await data_vault_service.list(db, principal)
    return [DataObjectView.model_validate(value) for value in values]


@router.get("/objects/{object_id}", operation_id="data_objects_get", response_model=DataObjectView)
async def get_object(
    object_id: UUID,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    db: AsyncSession = Depends(get_scoped_session),
) -> DataObjectView:
    try:
        return DataObjectView.model_validate(await data_vault_service.get(db, principal, object_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/objects/{object_id}/grants", operation_id="data_grants_create", status_code=201)
async def create_grant(
    object_id: UUID,
    body: DataGrantCreateRequest,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    db: AsyncSession = Depends(get_scoped_session),
) -> dict[str, str]:
    try:
        value = await data_vault_service.create_grant(db, principal, object_id, body)
        await db.flush()
        return {"grant_id": str(value.id), "status": value.status}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete(
    "/objects/{object_id}", operation_id="data_objects_delete", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_object(
    object_id: UUID,
    principal: AuthenticatedPrincipal = Depends(get_principal),
    correlation_id: UUID = Depends(get_correlation_id),
    db: AsyncSession = Depends(get_scoped_session),
) -> Response:
    try:
        await data_vault_service.delete(db, principal, object_id, correlation_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
