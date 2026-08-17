from fastapi import APIRouter, Request

from api.endpoints.deps import AdminContextDep
from api.rate_limit import limiter, rate
from crud import updates
from schemas import UpdateApplyPayload, UpdateApplyStatus

router = APIRouter(tags=["updates"])


@router.get(
    "/apply/status",
    name="updates:apply-status",
    response_model=UpdateApplyStatus,
)
async def get_apply_status() -> UpdateApplyStatus:
    return UpdateApplyStatus(**updates.get_apply_status())


@router.post(
    "/apply",
    name="updates:apply",
    response_model=UpdateApplyStatus,
)
@limiter.limit(rate("3/hour"))
async def apply_update(
    request: Request,
    body: UpdateApplyPayload,
    context: AdminContextDep,
) -> UpdateApplyStatus:
    return UpdateApplyStatus(**updates.request_update(body.target))
