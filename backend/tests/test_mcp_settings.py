import pytest
from pydantic import ValidationError

from settings import APISettings


def test_mcp_public_url_requires_https_outside_local_networks() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        APISettings(mcp_public_url="http://example.com/mcp")
    with pytest.raises(ValidationError, match="credentials"):
        APISettings(mcp_public_url="https://user@example.com/mcp?debug=1")

    assert str(APISettings(mcp_public_url="http://127.0.0.1:8000/mcp").mcp_public_url)
    assert str(APISettings(mcp_public_url="http://192.168.1.10/mcp").mcp_public_url)
    assert str(
        APISettings(mcp_public_url="https://vault.example.com/mcp").mcp_public_url
    )
