import pytest

from helpers import (
    create_user_keypair,
    decrypt_user_private_key,
    encrypt_user_private_key,
    generate_entry_key,
    unwrap_entry_key,
    wrap_entry_key,
)


def test_entry_key_can_be_shared_without_sharing_user_private_keys() -> None:
    alice_key = generate_entry_key()
    alice_public, alice_private = create_user_keypair(alice_key)
    bob_key = generate_entry_key()
    bob_public, bob_private = create_user_keypair(bob_key)
    entry_key = generate_entry_key()
    context = b"password:42"

    alice_wrapped = wrap_entry_key(alice_public, entry_key, context)
    bob_wrapped = wrap_entry_key(bob_public, entry_key, context)

    assert (
        unwrap_entry_key(
            decrypt_user_private_key(alice_key, alice_private), alice_wrapped, context
        )
        == entry_key
    )
    assert (
        unwrap_entry_key(
            decrypt_user_private_key(bob_key, bob_private), bob_wrapped, context
        )
        == entry_key
    )
    with pytest.raises(ValueError, match="entry key"):
        unwrap_entry_key(
            decrypt_user_private_key(bob_key, bob_private),
            bob_wrapped,
            b"password:43",
        )

    alice_private_raw = decrypt_user_private_key(alice_key, alice_private)
    rotated_private = encrypt_user_private_key(alice_key, alice_private_raw)
    assert decrypt_user_private_key(alice_key, rotated_private) == alice_private_raw


def test_wrapped_entry_key_rejects_another_users_private_key() -> None:
    alice_key = generate_entry_key()
    alice_public, _ = create_user_keypair(alice_key)
    bob_key = generate_entry_key()
    _, bob_private = create_user_keypair(bob_key)

    wrapped = wrap_entry_key(alice_public, generate_entry_key())

    with pytest.raises(ValueError, match="entry key"):
        unwrap_entry_key(decrypt_user_private_key(bob_key, bob_private), wrapped)
