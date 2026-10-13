class VaultError(Exception):
    """Base class for errors the vault core raises on purpose. Their message is
    shown to the client, so it must never contain a secret."""


class InvalidRequest(VaultError):
    pass


class Forbidden(VaultError):
    pass


class InvalidKey(Forbidden):
    pass


class NotFound(VaultError):
    pass


class SessionRequired(VaultError):
    pass


class VaultBusy(VaultError):
    pass
