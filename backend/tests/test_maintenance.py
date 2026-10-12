import json

import httpx
import pytest

from api.maintenance import ALLOWED_DURING_MAINTENANCE
from main import app
from tests.support import auth, create_vault, run_alembic
from tests.support import update_control_dir as control_dir


def _maintenance() -> None:
    (control_dir() / "maintenance.json").write_text(
        json.dumps({"protocol": 2, "id": "a" * 32, "target": "9.9.9"})
    )


@pytest.mark.parametrize(
    "path",
    ["/meta", "/health", "/updates/apply/status", "/master_password/status"],
    ids=str,
)
async def test_status_routes_answer_during_maintenance(
    client: httpx.AsyncClient, path: str
) -> None:
    _maintenance()

    resp = await client.get(path)

    assert resp.status_code == 200, resp.text


API_ROUTES = sorted(
    (method.upper(), path)
    for path, operations in app.openapi()["paths"].items()
    if path.startswith("/api")
    for method in operations
)
CLOSED_ROUTES = [
    route for route in API_ROUTES if route not in ALLOWED_DURING_MAINTENANCE
]


def test_maintenance_leaves_only_status_routes_open() -> None:
    assert set(API_ROUTES) - set(CLOSED_ROUTES) == ALLOWED_DURING_MAINTENANCE


@pytest.mark.parametrize("route", CLOSED_ROUTES, ids=" ".join)
async def test_every_other_route_is_closed_during_maintenance(
    client: httpx.AsyncClient, route: tuple[str, str]
) -> None:
    key = await create_vault(client)
    _maintenance()
    method, path = route
    url = path.removeprefix("/api").replace("{password_name}", "github")
    url = url.replace("{attachment_id}", "1")

    resp = await client.request(method, url, headers=auth(key), json={})

    assert resp.status_code == 503, resp.text
    assert resp.json()["code"] == "maintenance"
    assert resp.headers["retry-after"] == "30"


async def test_maintenance_answers_carry_cors_headers(
    client: httpx.AsyncClient,
) -> None:
    _maintenance()
    origin = "http://localhost:3000"

    preflight = await client.options(
        "/passwords",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-ciphermoth-session",
        },
    )
    blocked = await client.get("/passwords", headers={"Origin": origin})

    assert preflight.status_code == 200
    assert blocked.status_code == 503
    assert blocked.headers["access-control-allow-origin"] == origin


async def test_nothing_is_written_during_maintenance(
    client: httpx.AsyncClient,
) -> None:
    key = await create_vault(client)
    _maintenance()

    entry = {"password_name": "late", "password_value": "secret-Value-1"}
    resp = await client.post("/passwords/create", headers=auth(key), json=entry)
    (control_dir() / "maintenance.json").unlink()
    listing = await client.get("/passwords", headers=auth(key))
    after = await client.post("/passwords/create", headers=auth(key), json=entry)

    assert resp.status_code == 503
    assert listing.status_code == 200
    assert listing.json() == []
    assert after.status_code == 200, after.text


async def test_health_reports_a_current_schema(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["schema"] == "current"
    assert body["maintenance"] is False


async def test_health_reports_a_schema_that_is_not_at_the_release_head(
    client: httpx.AsyncClient,
) -> None:
    run_alembic("stamp", "8b9c0d1e2f3a")
    try:
        resp = await client.get("/health")
    finally:
        run_alembic("stamp", "head")

    assert resp.status_code == 503
    assert resp.json()["schema"] == "pending"
    assert resp.json()["status"] == "error"
