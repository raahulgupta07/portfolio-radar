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

    # How the worker reaches the gateway (MCP over HTTP) and how its jobs sign in (app/servicetokens.py).
    gateway_url: str = "http://localhost:8000"
    # token: the fixed *_TOKEN values below (dev). managed_identity: Entra tokens from Azure managed identities.
    service_auth: Literal["token", "managed_identity"] = "token"
    gateway_scope: str = ""  # e.g. api://city-mcp-gateway/.default
    adapter_client_id: str = ""
    radar_job_client_id: str = ""
    radar_agent_client_id: str = ""
    notifier_client_id: str = ""
    adapter_token: str = "dev-adapter"

    # City SSO (Microsoft Entra ID). When ENTRA_TENANT_ID is set, the gateway accepts Entra access tokens.
    entra_tenant_id: str = ""
    entra_audience: str = ""  # the gateway's API app ID URI or client ID
    entra_default_roles: list[str] = Field(default_factory=lambda: ["viewer"])  # any signed-in employee
    entra_group_roles: dict[str, list[str]] = Field(default_factory=dict)  # Entra group object ID -> roles
    # Apps signing in as themselves (client credentials): app ID -> {"kind": "agent"|"service", "id": ..., "roles": [...]}
    entra_apps: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # 2030 aspirations (strategy tags). Tags are set in the trackers; this list shows gaps.
    strategy_aspirations: list[str] = Field(default_factory=lambda: [
        "Innovative Market Leader", "Benchmark of Excellence", "Employer of Choice",
        "Preferred Business Partner", "Homegrown Champion"])

    # Radar
    radar_token: str = "dev-radar-job"  # the nightly Radar job (service, role radar)
    radar_agent_token: str = "dev-radar"  # the chat agent (agent)
    notifier_token: str = "dev-notifier"
    # LLM for Radar's words (OpenAI-compatible: CityGPT, Azure OpenAI, or a proxy). Empty = rule-based answers.
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    # Notifier channels. Empty = not set up (dev writes to the log instead).
    teams_webhook_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "portfolio-radar@cityholdings.com.mm"
    notify_email_to: list[str] = Field(default_factory=list)

    # Secret store. The app keeps only secret names (kv://name); values live here.
    # keyvault: Azure Key Vault (production). local: a file, dev and test only.
    secret_store: Literal["local", "keyvault"] = "local"
    secret_store_path: Path = BACKEND_DIR / ".secrets" / "dev-secrets.json"
    key_vault_url: str = ""  # e.g. https://city-portfolio-kv.vault.azure.net/
    # Seconds between re-reads of agents and SSO settings saved in Admin.
    identity_refresh_seconds: float = 30.0

    rate_limit_per_minute: int = 120
    # Services (nightly sync, Radar job, notifier): the sync makes about 4 calls per project.
    service_rate_limit_per_minute: int = 6000
    # Seconds a tool's on/off status is cached before re-reading the registry.
    registry_cache_seconds: float = 5.0
    # Longest argument summary kept in the audit log.
    audit_args_max_chars: int = 2000


@lru_cache
def get_settings() -> Settings:
    return Settings()
