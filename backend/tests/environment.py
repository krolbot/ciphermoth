import os
import tempfile
from urllib.parse import urlparse

DEFAULT_TEST_DB_URL = (
    "postgresql://ciphermoth_test:ciphermoth_test@127.0.0.1:55432/ciphermoth_test"
)
_SAFE_HOSTS = {"127.0.0.1", "localhost", "::1"}


def configure_test_environment() -> None:
    url = urlparse(os.environ.get("CIPHERMOTH_TEST_DB_URL", DEFAULT_TEST_DB_URL))
    database = url.path.lstrip("/")
    if url.hostname not in _SAFE_HOSTS or not database.endswith("_test"):
        raise RuntimeError(
            "Refusing to run the test suite: CIPHERMOTH_TEST_DB_URL must point at a "
            "local database whose name ends in '_test'. The suite truncates every "
            "table it touches."
        )
    os.environ["POSTGRES_HOST"] = url.hostname or "127.0.0.1"
    os.environ["POSTGRES_PORT"] = str(url.port or 5432)
    os.environ["POSTGRES_DB"] = database
    os.environ["POSTGRES_USER"] = url.username or ""
    os.environ["POSTGRES_PASSWORD"] = url.password or ""
    os.environ["CIPHERMOTH_RATE_LIMIT"] = "100000/hour"
    os.environ.setdefault(
        "UPDATE_CONTROL_DIR", tempfile.mkdtemp(prefix="ciphermoth-update-control-")
    )
