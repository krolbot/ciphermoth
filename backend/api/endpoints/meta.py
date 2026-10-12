from fastapi import APIRouter

from api.legacy import legacy_key_auth_enabled
from schemas import MetaResponse
from settings import get_api_settings

router = APIRouter(tags=["meta"])


@router.get("", name="meta:get", response_model=MetaResponse)
def get_meta() -> MetaResponse:
    features = ["entry-names-with-slash", "vault-sessions"]
    if legacy_key_auth_enabled():
        features.append("legacy-key-auth")
    return MetaResponse(version=get_api_settings().version, features=features)
