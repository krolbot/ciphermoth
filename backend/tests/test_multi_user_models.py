from sqlalchemy import inspect

from models import (
    InstanceStateModel,
    PasswordAccessModel,
    PasswordModel,
    SessionModel,
    SettingsModel,
    UserModel,
)


def test_multi_user_storage_contract() -> None:
    assert {column.name for column in inspect(InstanceStateModel).columns} == {
        "id",
        "bootstrapped_at",
    }
    assert {column.name for column in inspect(UserModel).columns} >= {
        "id",
        "username",
        "role",
        "active",
        "must_change_password",
        "salt",
        "public_key",
        "encrypted_private_key",
    }
    assert {column.name for column in inspect(SessionModel).columns} >= {
        "user_id",
        "token_hash",
        "expires_at",
    }
    assert {column.name for column in inspect(PasswordAccessModel).columns} >= {
        "password_id",
        "user_id",
        "permission",
        "wrapped_key",
        "encrypted_preferences",
    }
    assert {column.name for column in inspect(PasswordModel).columns} >= {
        "owner_id",
        "encryption_version",
        "encrypted_payload",
    }
    assert "user_id" in {column.name for column in inspect(SettingsModel).columns}
