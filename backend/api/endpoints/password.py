from fastapi import APIRouter

from api.endpoints.deps import EncryptedPasswordCRUDDep, VaultContextDep
from schemas import (
    EncryptedAttachmentPayload,
    EncryptedAttachmentResponse,
    EncryptedPasswordCreatePayload,
    EncryptedPasswordResponse,
    EncryptedPasswordUpdatePayload,
    EncryptedPreferencesUpdatePayload,
    LegacyPasswordResponse,
    PasswordMigrationPayload,
    ShareGrant,
    ShareUpdatePayload,
    SimpleDetailSchema,
)

router = APIRouter(tags=["passwords"])


@router.get("", response_model=list[EncryptedPasswordResponse])
async def get_passwords(
    crud: EncryptedPasswordCRUDDep, context: VaultContextDep
) -> list[EncryptedPasswordResponse]:
    return await crud.list_passwords(context)


@router.get("/trash", response_model=list[EncryptedPasswordResponse])
async def get_trash(
    crud: EncryptedPasswordCRUDDep, context: VaultContextDep
) -> list[EncryptedPasswordResponse]:
    return await crud.list_passwords(context, deleted=True)


@router.get("/legacy", response_model=list[LegacyPasswordResponse])
async def list_legacy_passwords(
    crud: EncryptedPasswordCRUDDep, context: VaultContextDep
) -> list[LegacyPasswordResponse]:
    return await crud.list_legacy(context)


@router.put("/legacy/{password_id}", response_model=EncryptedPasswordResponse)
async def migrate_legacy_password(
    password_id: int,
    payload: PasswordMigrationPayload,
    crud: EncryptedPasswordCRUDDep,
    context: VaultContextDep,
) -> EncryptedPasswordResponse:
    return await crud.migrate(context, password_id, payload)


@router.post("", response_model=EncryptedPasswordResponse)
async def create_password(
    body: EncryptedPasswordCreatePayload,
    crud: EncryptedPasswordCRUDDep,
    context: VaultContextDep,
) -> EncryptedPasswordResponse:
    return await crud.create(context, **body.model_dump())


@router.get("/{password_id}", response_model=EncryptedPasswordResponse)
async def get_password(
    password_id: int,
    crud: EncryptedPasswordCRUDDep,
    context: VaultContextDep,
) -> EncryptedPasswordResponse:
    return await crud.get(context, password_id)


@router.put("/{password_id}", response_model=EncryptedPasswordResponse)
async def update_password(
    password_id: int,
    body: EncryptedPasswordUpdatePayload,
    crud: EncryptedPasswordCRUDDep,
    context: VaultContextDep,
) -> EncryptedPasswordResponse:
    return await crud.update(context, password_id, **body.model_dump())


@router.patch("/{password_id}/preferences", response_model=EncryptedPasswordResponse)
async def set_preferences(
    password_id: int,
    body: EncryptedPreferencesUpdatePayload,
    crud: EncryptedPasswordCRUDDep,
    context: VaultContextDep,
) -> EncryptedPasswordResponse:
    return await crud.set_preferences(
        context,
        password_id,
        encrypted_preferences=body.encrypted_preferences,
    )


@router.delete("/{password_id}", response_model=EncryptedPasswordResponse)
async def delete_password(
    password_id: int,
    crud: EncryptedPasswordCRUDDep,
    context: VaultContextDep,
) -> EncryptedPasswordResponse:
    return await crud.set_deleted(context, password_id, deleted=True)


@router.post("/{password_id}/restore", response_model=EncryptedPasswordResponse)
async def restore_password(
    password_id: int,
    crud: EncryptedPasswordCRUDDep,
    context: VaultContextDep,
) -> EncryptedPasswordResponse:
    return await crud.set_deleted(context, password_id, deleted=False)


@router.delete("/{password_id}/purge", response_model=SimpleDetailSchema)
async def purge_password(
    password_id: int,
    crud: EncryptedPasswordCRUDDep,
    context: VaultContextDep,
) -> SimpleDetailSchema:
    await crud.delete(context, password_id)
    return SimpleDetailSchema(detail="Password permanently deleted.")


@router.get("/{password_id}/shares", response_model=list[ShareGrant])
async def list_shares(
    password_id: int,
    crud: EncryptedPasswordCRUDDep,
    context: VaultContextDep,
) -> list[ShareGrant]:
    return await crud.list_shares(context, password_id)


@router.put("/{password_id}/shares/{user_id}", response_model=ShareGrant)
async def set_share(
    password_id: int,
    user_id: int,
    body: ShareUpdatePayload,
    crud: EncryptedPasswordCRUDDep,
    context: VaultContextDep,
) -> ShareGrant:
    return await crud.share(
        context,
        password_id,
        user_id,
        permission=body.permission,
        wrapped_key=body.wrapped_key,
    )


@router.delete("/{password_id}/shares/{user_id}", response_model=SimpleDetailSchema)
async def revoke_share(
    password_id: int,
    user_id: int,
    crud: EncryptedPasswordCRUDDep,
    context: VaultContextDep,
) -> SimpleDetailSchema:
    await crud.revoke_share(context, password_id, user_id)
    return SimpleDetailSchema(detail="Access revoked.")


@router.get(
    "/{password_id}/attachments", response_model=list[EncryptedAttachmentResponse]
)
async def list_attachments(
    password_id: int,
    crud: EncryptedPasswordCRUDDep,
    context: VaultContextDep,
) -> list[EncryptedAttachmentResponse]:
    return await crud.list_attachments(context, password_id)


@router.post("/{password_id}/attachments", response_model=EncryptedAttachmentResponse)
async def add_attachment(
    password_id: int,
    body: EncryptedAttachmentPayload,
    crud: EncryptedPasswordCRUDDep,
    context: VaultContextDep,
) -> EncryptedAttachmentResponse:
    return await crud.add_attachment(
        context, password_id, encrypted_payload=body.encrypted_payload
    )


@router.put(
    "/{password_id}/attachments", response_model=list[EncryptedAttachmentResponse]
)
async def replace_attachments(
    password_id: int,
    body: list[EncryptedAttachmentPayload],
    crud: EncryptedPasswordCRUDDep,
    context: VaultContextDep,
) -> list[EncryptedAttachmentResponse]:
    return await crud.replace_attachments(
        context,
        password_id,
        encrypted_payloads=[item.encrypted_payload for item in body],
    )


@router.get(
    "/{password_id}/attachments/{attachment_id}",
    response_model=EncryptedAttachmentResponse,
)
async def get_attachment(
    password_id: int,
    attachment_id: int,
    crud: EncryptedPasswordCRUDDep,
    context: VaultContextDep,
) -> EncryptedAttachmentResponse:
    return await crud.get_attachment(context, password_id, attachment_id)


@router.delete(
    "/{password_id}/attachments/{attachment_id}", response_model=SimpleDetailSchema
)
async def delete_attachment(
    password_id: int,
    attachment_id: int,
    crud: EncryptedPasswordCRUDDep,
    context: VaultContextDep,
) -> SimpleDetailSchema:
    await crud.delete_attachment(context, password_id, attachment_id)
    return SimpleDetailSchema(detail="Attachment deleted.")
