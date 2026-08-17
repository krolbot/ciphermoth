import io
from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import APIRouter, Form, Request, UploadFile
from starlette.responses import StreamingResponse

from api.endpoints.deps import AttachmentCRUDDep, PasswordCRUDDep, VaultContextDep
from api.exceptions import TypesMismatchError
from api.rate_limit import limiter, rate
from schemas import (
    AttachmentResponse,
    FavoriteUpdatePayload,
    MasterPassword,
    OnConflict,
    Password,
    PasswordCreate,
    PasswordDelete,
    PasswordImportResult,
    PasswordResponse,
    PasswordUpdate,
    ShareGrant,
    ShareUpdatePayload,
    SimpleDetailSchema,
)

router = APIRouter(tags=["passwords"])

_MAX_IMPORT_FILE_BYTES = 10 * 1024 * 1024
_MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024


async def _read_capped(file: UploadFile, max_bytes: int, message: str) -> bytes:
    if file.size is not None and file.size > max_bytes:
        raise TypesMismatchError(message)
    data = await file.read()
    if len(data) > max_bytes:
        raise TypesMismatchError(message)
    return data


def _safe_content_disposition(filename: str) -> str:
    cleaned = filename.replace("\r", "").replace("\n", "").replace('"', "")
    cleaned = cleaned.strip() or "attachment"
    ascii_name = cleaned.encode("ascii", "replace").decode("ascii").replace("?", "_")
    quoted = quote(cleaned, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted}"


@router.get("", response_model=list[PasswordResponse])
async def get_passwords(
    crud: PasswordCRUDDep, context: VaultContextDep
) -> list[PasswordResponse]:
    return await crud.get_passwords(context)


@router.get("/trash", response_model=list[PasswordResponse])
async def get_trash(
    crud: PasswordCRUDDep, context: VaultContextDep
) -> list[PasswordResponse]:
    return await crud.get_trash(context)


@router.post("", response_model=PasswordCreate)
async def create_password(
    password: Password, crud: PasswordCRUDDep, context: VaultContextDep
) -> PasswordCreate:
    return await crud.create_password(password, context)


@router.post("/import", response_model=PasswordImportResult)
@limiter.limit(rate("5/hour"))
async def import_passwords(
    request: Request,
    file: UploadFile,
    crud: PasswordCRUDDep,
    context: VaultContextDep,
    master_password: str = Form(...),
    on_conflict: OnConflict = Form(OnConflict.skip),
) -> PasswordImportResult:
    file_bytes = await _read_capped(
        file, _MAX_IMPORT_FILE_BYTES, "File too large. Maximum allowed size is 10 MB."
    )
    return await crud.import_passwords(
        file_bytes, master_password, context, on_conflict
    )


@router.post("/import/csv", response_model=PasswordImportResult)
@limiter.limit(rate("5/hour"))
async def import_passwords_csv(
    request: Request,
    file: UploadFile,
    crud: PasswordCRUDDep,
    context: VaultContextDep,
    on_conflict: OnConflict = Form(OnConflict.skip),
) -> PasswordImportResult:
    file_bytes = await _read_capped(
        file, _MAX_IMPORT_FILE_BYTES, "File too large. Maximum allowed size is 10 MB."
    )
    return await crud.import_passwords_csv(file_bytes, context, on_conflict)


@router.post("/backup")
@limiter.limit(rate("3/hour"))
async def backup_passwords(
    request: Request,
    body: MasterPassword,
    crud: PasswordCRUDDep,
    context: VaultContextDep,
) -> StreamingResponse:
    data = await crud.create_backup(body.master_password, context)
    filename = f"ciphermoth_backup_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.zip"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{password_id}", response_model=PasswordResponse)
async def get_password(
    password_id: int, crud: PasswordCRUDDep, context: VaultContextDep
) -> PasswordResponse:
    return await crud.get_password(password_id, context)


@router.put("/{password_id}", response_model=PasswordUpdate)
async def update_password(
    password_id: int,
    password: Password,
    crud: PasswordCRUDDep,
    context: VaultContextDep,
) -> PasswordUpdate:
    return await crud.update_password(password_id, password, context)


@router.patch("/{password_id}/favorite", response_model=PasswordUpdate)
async def set_favorite(
    password_id: int,
    body: FavoriteUpdatePayload,
    crud: PasswordCRUDDep,
    context: VaultContextDep,
) -> PasswordUpdate:
    return await crud.set_favorite(password_id, body.favorite, context)


@router.delete("/{password_id}", response_model=PasswordDelete)
async def delete_password(
    password_id: int, crud: PasswordCRUDDep, context: VaultContextDep
) -> PasswordDelete:
    return await crud.delete_password(password_id, context)


@router.post("/{password_id}/restore", response_model=PasswordUpdate)
async def restore_password(
    password_id: int, crud: PasswordCRUDDep, context: VaultContextDep
) -> PasswordUpdate:
    return await crud.restore_password(password_id, context)


@router.delete("/{password_id}/purge", response_model=PasswordDelete)
async def purge_password(
    password_id: int, crud: PasswordCRUDDep, context: VaultContextDep
) -> PasswordDelete:
    return await crud.purge_password(password_id, context)


@router.get("/{password_id}/shares", response_model=list[ShareGrant])
async def list_shares(
    password_id: int, crud: PasswordCRUDDep, context: VaultContextDep
) -> list[ShareGrant]:
    return await crud.list_shares(password_id, context)


@router.put("/{password_id}/shares/{user_id}", response_model=ShareGrant)
async def set_share(
    password_id: int,
    user_id: int,
    body: ShareUpdatePayload,
    crud: PasswordCRUDDep,
    context: VaultContextDep,
) -> ShareGrant:
    return await crud.set_share(password_id, user_id, body.permission, context)


@router.delete("/{password_id}/shares/{user_id}", response_model=SimpleDetailSchema)
async def revoke_share(
    password_id: int,
    user_id: int,
    crud: PasswordCRUDDep,
    context: VaultContextDep,
) -> SimpleDetailSchema:
    await crud.revoke_share(password_id, user_id, context)
    return SimpleDetailSchema(detail="Access revoked.")


@router.get("/{password_id}/attachments", response_model=list[AttachmentResponse])
async def list_attachments(
    password_id: int, crud: AttachmentCRUDDep, context: VaultContextDep
) -> list[AttachmentResponse]:
    return await crud.list_attachments(password_id, context)


@router.post("/{password_id}/attachments", response_model=AttachmentResponse)
@limiter.limit(rate("60/hour"))
async def add_attachment(
    request: Request,
    password_id: int,
    file: UploadFile,
    crud: AttachmentCRUDDep,
    context: VaultContextDep,
) -> AttachmentResponse:
    data = await _read_capped(
        file, _MAX_ATTACHMENT_BYTES, "Attachment too large. Maximum size is 5 MB."
    )
    return await crud.add_attachment(
        password_id,
        file.filename or "attachment",
        file.content_type,
        data,
        context,
    )


@router.get("/{password_id}/attachments/{attachment_id}")
async def download_attachment(
    password_id: int,
    attachment_id: int,
    crud: AttachmentCRUDDep,
    context: VaultContextDep,
) -> StreamingResponse:
    filename, content_type, data = await crud.get_attachment_data(
        password_id, attachment_id, context
    )
    return StreamingResponse(
        io.BytesIO(data),
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": _safe_content_disposition(filename)},
    )


@router.delete(
    "/{password_id}/attachments/{attachment_id}", response_model=PasswordDelete
)
async def delete_attachment(
    password_id: int,
    attachment_id: int,
    crud: AttachmentCRUDDep,
    context: VaultContextDep,
) -> PasswordDelete:
    await crud.delete_attachment(password_id, attachment_id, context)
    return PasswordDelete(deleted=True, detail="Attachment deleted.")
