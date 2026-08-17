from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from ipaddress import ip_address
from typing import Any

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _package_version() -> str:
    try:
        return version("backend")
    except PackageNotFoundError:
        import pathlib
        import tomllib

        try:
            pyproject = pathlib.Path(__file__).with_name("pyproject.toml")
            return tomllib.loads(pyproject.read_text())["project"]["version"]
        except Exception:
            return "0.0.0"


class APISettings(BaseSettings):
    debug: bool = False
    docs_url: str = "/docs"
    openapi_url: str = "/openapi.json"
    redoc_url: str = "/redoc"
    title: str = "CipherMoth API Service"
    version: str = _package_version()
    disable_docs: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]
    mcp_public_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8000/mcp")
    mcp_max_request_bytes: int = Field(default=1_048_576, ge=1_024, le=4_194_304)

    @field_validator("mcp_public_url")
    @classmethod
    def _secure_mcp_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.username or value.password or value.query or value.fragment:
            raise ValueError(
                "MCP public URL cannot contain credentials, query, or fragment."
            )
        if (value.path or "").rstrip("/") != "/mcp":
            raise ValueError("MCP public URL path must be /mcp.")
        if value.scheme == "https":
            return value
        host = value.host or ""
        if host == "localhost":
            return value
        try:
            address = ip_address(host)
        except ValueError:
            address = None
        if (
            value.scheme == "http"
            and address is not None
            and (address.is_private or address.is_loopback)
        ):
            return value
        raise ValueError("MCP requires HTTPS outside local networks.")

    @property
    def fastapi_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "debug": self.debug,
            "docs_url": self.docs_url,
            "openapi_url": self.openapi_url,
            "redoc_url": self.redoc_url,
            "title": self.title,
            "version": self.version,
        }
        if self.disable_docs:
            kwargs.update({"docs_url": None, "openapi_url": None, "redoc_url": None})
        return kwargs

    model_config = {"validate_assignment": True}


class DBSettings(BaseSettings):
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_db: str = "ciphermoth"
    postgres_user: str = "ciphermoth"
    postgres_password: str = "ciphermoth"
    pool_recycle: int = 900

    model_config = SettingsConfigDict(env_file=".db.env", extra="ignore")


@lru_cache
def get_api_settings() -> APISettings:
    return APISettings()


@lru_cache
def get_db_settings() -> DBSettings:
    return DBSettings()
