"""Settings come from environment variables (or a local .env). No secrets in code."""

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "postgresql+psycopg://radar:radar@localhost:5432/radar"

    source_mode: Literal["mock", "live"] = "mock"
    sample_data_path: Path = BACKEND_DIR.parent / "design" / "sample-data.json"

    # token -> {"kind": "human"|"agent"|"service", "id": str, "roles": [str]}
    # Only honoured when app_env is dev or test. Production uses City SSO.
    dev_tokens: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # Host headers the MCP endpoints accept (protects against DNS rebinding).
    mcp_allowed_hosts: list[str] = Field(default_factory=lambda: ["127.0.0.1:*", "localhost:*", "mcp:*"])
    mcp_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:*", "http://127.0.0.1:*"])

    rate_limit_per_minute: int = 120
    # Seconds a tool's on/off status is cached before re-reading the registry.
    registry_cache_seconds: float = 5.0
    # Longest argument summary kept in the audit log.
    audit_args_max_chars: int = 2000


@lru_cache
def get_settings() -> Settings:
    return Settings()
