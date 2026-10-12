import asyncio

import asyncpg
import pytest

from tests.support import admin_connection
from tests.test_updater_units import updater

LIVE = "swaptest_vault"
REPLACEMENT = "swaptest_vault_restore_" + "a" * 32
RETIRED = "swaptest_vault_failed_" + "a" * 32
NAMES = (LIVE, REPLACEMENT, RETIRED)
TERMINATE = (
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
    "WHERE datname IN ({names}) AND pid <> pg_backend_pid()"
)


async def _admin() -> asyncpg.Connection:
    return await admin_connection("postgres")


async def _create(conn: asyncpg.Connection, name: str, marker: str) -> None:
    await conn.execute(f'CREATE DATABASE "{name}"')
    other = await admin_connection(name)
    try:
        await other.execute("CREATE TABLE marker (value text)")
        await other.execute("INSERT INTO marker VALUES ($1)", marker)
    finally:
        await other.close()


async def _marker(name: str) -> str:
    conn = await admin_connection(name)
    try:
        return await conn.fetchval("SELECT value FROM marker")
    finally:
        await conn.close()


async def _databases(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch("SELECT datname FROM pg_database")
    return {row[0] for row in rows} & set(NAMES)


@pytest.fixture
async def admin():
    conn = await _admin()
    for name in NAMES:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    await _create(conn, LIVE, "old")
    await _create(conn, REPLACEMENT, "new")
    try:
        yield conn
    finally:
        for name in NAMES:
            await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.close()


def _swap() -> str:
    return updater.swap_sql(LIVE, REPLACEMENT, RETIRED, True)


async def test_the_swap_replaces_the_vault_in_one_transaction(admin) -> None:
    await admin.execute(_swap())

    assert await _databases(admin) == {LIVE, RETIRED}
    assert await _marker(LIVE) == "new"
    assert await _marker(RETIRED) == "old"


async def test_a_failure_between_the_renames_keeps_the_original_vault(admin) -> None:
    first, second = (
        _swap().removeprefix("BEGIN; ").removesuffix("; COMMIT;").split("; ")
    )

    with pytest.raises(asyncpg.DivisionByZeroError):
        await admin.execute(f"BEGIN; {first}; SELECT 1/0; {second}; COMMIT;")
    await admin.execute("ROLLBACK")

    assert await _databases(admin) == {LIVE, REPLACEMENT}
    assert await _marker(LIVE) == "old"


async def test_a_missing_replacement_keeps_the_original_vault(admin) -> None:
    await admin.execute(f'DROP DATABASE "{REPLACEMENT}"')

    with pytest.raises(asyncpg.InvalidCatalogNameError):
        await admin.execute(_swap())
    await admin.execute("ROLLBACK")

    assert await _databases(admin) == {LIVE}
    assert await _marker(LIVE) == "old"


async def test_a_connection_lost_mid_swap_keeps_the_original_vault(admin) -> None:
    first, second = (
        _swap().removeprefix("BEGIN; ").removesuffix("; COMMIT;").split("; ")
    )
    victim = await _admin()
    pid = await victim.fetchval("SELECT pg_backend_pid()")
    swap = asyncio.create_task(
        victim.execute(f"BEGIN; {first}; SELECT pg_sleep(30); {second}; COMMIT;")
    )
    await asyncio.sleep(1)
    assert not swap.done()

    await admin.execute("SELECT pg_terminate_backend($1)", pid)
    with pytest.raises((asyncpg.PostgresError, asyncpg.InterfaceError, OSError)):
        await swap

    assert await _databases(admin) == {LIVE, REPLACEMENT}
    assert await _marker(LIVE) == "old"
    assert await _marker(REPLACEMENT) == "new"


async def test_a_lingering_connection_blocks_the_swap_until_terminated(
    admin,
) -> None:
    lingering = await admin_connection(LIVE)
    try:
        with pytest.raises(asyncpg.ObjectInUseError):
            await admin.execute(_swap())
        await admin.execute("ROLLBACK")
        assert await _databases(admin) == {LIVE, REPLACEMENT}
        assert await _marker(LIVE) == "old"

        names = ", ".join(f"'{name}'" for name in (LIVE, REPLACEMENT))
        await admin.execute(TERMINATE.format(names=names))
        await admin.execute(_swap())
    finally:
        await lingering.close()

    assert await _marker(LIVE) == "new"


async def test_a_swap_without_a_live_vault_only_renames_the_replacement(
    admin,
) -> None:
    await admin.execute(f'DROP DATABASE "{LIVE}" WITH (FORCE)')

    await admin.execute(updater.swap_sql(LIVE, REPLACEMENT, RETIRED, False))

    assert await _databases(admin) == {LIVE}
    assert await _marker(LIVE) == "new"


def test_the_updater_terminates_the_same_connections_before_swapping() -> None:
    source = updater.Postgres.swap.__code__.co_names
    assert "terminate" in source
    assert "swap_sql" in source
