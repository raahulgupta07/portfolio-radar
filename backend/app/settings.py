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

    # Health rule thresholds (PRD FR-17). Admins change them in Admin → Radar.
    health_overdue_days: int = 3
    health_behind_points: int = 15
    health_milestone_window_days: int = 7
    stale_days: int = 14

    # Nightly jobs (Asia/Yangon). Cron fields: minute hour day month weekday.
    timezone: str = "Asia/Yangon"
    sync_cron: str = "0 2 * * *"
    status_map_path: Path = BACKEND_DIR / "config" / "status_map.json"
    # Fix "today" for demos and tests (YYYY-MM-DD). Empty = the real date in `timezone`.
    today: str = ""

    # How the worker reaches the gateway (MCP over HTTP) and the service tokens it uses.
    gateway_url: str = "http://localhost:8000"
    adapter_token: str = "dev-adapter"

    rate_limit_per_minute: int = 120
    # Seconds a tool's on/off status is cached before re-reading the registry.
    registry_cache_seconds: float = 5.0
    # Longest argument summary kept in the audit log.
    audit_args_max_chars: int = 2000


@lru_cache
def get_settings() -> Settings:
    return Settings()
