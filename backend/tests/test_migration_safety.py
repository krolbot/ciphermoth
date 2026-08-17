import importlib.util
from pathlib import Path

import pytest

_MIGRATION = (
    Path(__file__).parents[1]
    / "migrations/ciphermoth/versions/a1b2c3d4e5f6_multi_user_sharing.py"
)


def test_multi_user_downgrade_refuses_to_destroy_bootstrapped_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = importlib.util.spec_from_file_location("multi_user_migration", _MIGRATION)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    class BootstrappedConnection:
        @staticmethod
        def scalar(statement: object) -> bool:
            assert "SELECT EXISTS" in str(statement)
            return True

    monkeypatch.setattr(migration.op, "get_bind", lambda: BootstrappedConnection())
    monkeypatch.setattr(
        migration.op,
        "drop_constraint",
        lambda *args, **kwargs: pytest.fail("downgrade mutated schema before guard"),
    )

    with pytest.raises(RuntimeError, match="per-entry encryption keys"):
        migration.downgrade()
