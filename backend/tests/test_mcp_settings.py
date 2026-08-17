from settings import APISettings


def test_mcp_has_no_public_url_setting() -> None:
    assert "mcp_public_url" not in APISettings.model_fields
