import os
import tempfile


def configure_test_environment() -> None:
    """Every test run gets its own throwaway data folder, so the suite can never
    open a real vault."""
    os.environ["CIPHERMOTH_DATA_DIR"] = tempfile.mkdtemp(prefix="ciphermoth-test-")
    os.environ["CIPHERMOTH_RATE_LIMIT"] = "100000/hour"
