"""
Compatibility policy for clients that predate vault sessions (v1.4.x and older).

Those clients unlock with ``POST /master_password/check``, receive the vault key
and send it back on every request in the ``x-ciphermoth-key-derivation`` header.
v1.5.x still accepts that, validated exactly as v1.4.7 did (the key must match
the vault's key check, under the same row lock), so v1.4.x CLIs and browser tabs
that were open during the update keep working. Clients that know about sessions
never ask for the key. Operators can refuse the header and ``/check`` today with
``CIPHERMOTH_LEGACY_KEY_AUTH=false``. Both are removed in ``REMOVED_IN``, and a
test fails once the package version reaches it while this module still exists.
"""

from settings import get_api_settings

LEGACY_KEY_HEADER = "x-ciphermoth-key-derivation"
REMOVED_IN = (1, 6, 0)
DEPRECATED_SINCE = "@1791763200"
DISABLED = (
    "This server no longer accepts the vault key from clients. Update the "
    "CipherMoth CLI, or reload the browser tab, and unlock again."
)


def legacy_key_auth_enabled() -> bool:
    return get_api_settings().legacy_key_auth
