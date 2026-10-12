from fastapi import (
    APIRouter,
    Depends,
    Request,
    Response,
    status,
)

from api.endpoints.deps import (
    CredentialDep,
    MasterPasswordCRUDDep,
    SessionTokenHeader,
    VaultAccessDep,
    VaultSessionsDep,
    get_vault_key,
    get_vault_key_for_rotation,
    require_master_password,
)
from api.legacy import DEPRECATED_SINCE, DISABLED, legacy_key_auth_enabled
from api.rate_limit import limiter, rate
from api.responses import inject_responses
from errors import Forbidden
from schemas import (
    MasterPassword,
    MasterPasswordCheck,
    MasterPasswordCreate,
    MasterPasswordCreatePayload,
    MasterPasswordStatus,
    MasterPasswordUpdate,
    MasterPasswordUpdatePayload,
    SimpleDetailSchema,
    VaultLock,
    VaultSessionStatus,
    VaultUnlock,
)

router = APIRouter(tags=["master-password"])

_UNLOCK_LIMIT = rate("30/hour")


@router.get(
    "/status",
    name="master-password:status",
    response_model=MasterPasswordStatus,
)
async def get_status(
    crud: MasterPasswordCRUDDep,
) -> MasterPasswordStatus:
    return MasterPasswordStatus(initialized=await crud.is_initialized())


@router.post(
    "/unlock",
    name="master-password:unlock",
    response_model=VaultUnlock,
    responses=inject_responses(
        {
            status.HTTP_404_NOT_FOUND: SimpleDetailSchema,
            status.HTTP_429_TOO_MANY_REQUESTS: SimpleDetailSchema,
        }
    ),
)
@limiter.shared_limit(_UNLOCK_LIMIT, scope="master-password:unlock")
async def unlock(
    request: Request,
    body: MasterPassword,
    access: VaultAccessDep,
) -> VaultUnlock:
    return await access.unlock(body.master_password)


@router.post(
    "/lock",
    name="master-password:lock",
    response_model=VaultLock,
)
async def lock(
    token: SessionTokenHeader, vault_sessions: VaultSessionsDep
) -> VaultLock:
    vault_sessions.revoke(token)
    return VaultLock(locked=True)


@router.get(
    "/session",
    name="master-password:session",
    response_model=VaultSessionStatus,
    dependencies=[Depends(require_master_password), Depends(get_vault_key)],
    responses=inject_responses({status.HTTP_403_FORBIDDEN: SimpleDetailSchema}),
)
async def get_session_status(
    access: VaultAccessDep, credential: CredentialDep
) -> VaultSessionStatus:
    return access.status(credential)


@router.post(
    "/check",
    name="master-password:check",
    response_model=MasterPasswordCheck,
    deprecated=True,
    responses=inject_responses(
        {
            status.HTTP_404_NOT_FOUND: SimpleDetailSchema,
            status.HTTP_403_FORBIDDEN: SimpleDetailSchema,
            status.HTTP_429_TOO_MANY_REQUESTS: SimpleDetailSchema,
        }
    ),
)
@limiter.shared_limit(_UNLOCK_LIMIT, scope="master-password:unlock")
async def check_master_password(
    request: Request,
    response: Response,
    body: MasterPassword,
    crud: MasterPasswordCRUDDep,
) -> MasterPasswordCheck:
    if not legacy_key_auth_enabled():
        raise Forbidden(DISABLED)
    response.headers["Deprecation"] = DEPRECATED_SINCE
    return await crud.check_master_password(master_password=body.master_password)


@router.post(
    "/create",
    name="master-password:create",
    response_model=MasterPasswordCreate,
    responses=inject_responses(
        {
            status.HTTP_403_FORBIDDEN: SimpleDetailSchema,
            status.HTTP_429_TOO_MANY_REQUESTS: SimpleDetailSchema,
        }
    ),
)
@limiter.limit(rate("5/hour"))
async def create_master_password(
    request: Request,
    body: MasterPasswordCreatePayload,
    access: VaultAccessDep,
) -> MasterPasswordCreate:
    return await access.create(body.master_password)


@router.patch(
    "/update",
    name="master-password:update",
    response_model=MasterPasswordUpdate,
    dependencies=[Depends(get_vault_key_for_rotation)],
    responses=inject_responses(
        {
            status.HTTP_404_NOT_FOUND: SimpleDetailSchema,
            status.HTTP_403_FORBIDDEN: SimpleDetailSchema,
            status.HTTP_400_BAD_REQUEST: SimpleDetailSchema,
            status.HTTP_429_TOO_MANY_REQUESTS: SimpleDetailSchema,
        }
    ),
)
@limiter.limit(rate("10/hour"))
async def update_master_password(
    request: Request,
    body: MasterPasswordUpdatePayload,
    access: VaultAccessDep,
) -> MasterPasswordUpdate:
    return await access.change_master_password(
        master_password=body.master_password,
        new_master_password=body.new_master_password,
    )
