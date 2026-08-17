from main import app
from schemas import AuthBootstrapPayload, AuthChallengeResponse, AuthStatus
from settings import APISettings


def test_legacy_migration_surface_is_removed() -> None:
    assert set(AuthStatus.model_fields) == {"initialized"}
    assert "legacy_migration_token" not in AuthBootstrapPayload.model_fields
    assert "legacy_user" not in AuthChallengeResponse.model_fields
    assert not hasattr(APISettings(), "ciphermoth_legacy_migration_token")

    paths = {path for route in app.routes if (path := getattr(route, "path", None))}
    assert "/api/passwords/legacy" not in paths
    assert "/api/passwords/legacy/{password_id}" not in paths
