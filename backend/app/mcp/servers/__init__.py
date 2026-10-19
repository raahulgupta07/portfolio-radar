"""All MCP servers the gateway serves. Add a new server module here."""

from typing import Any

from app.connectors import SOURCES, build_connectors
from app.mcp.registry import Registry
from app.mcp.servers import admin, connections, notify, omni, portfolio, radar, system  # noqa: F401  connections adds to admin
from app.mcp.servers.sources import make_source_server
from app.secretstore import build_secret_store
from app.settings import Settings


def build_registry(settings: Settings) -> Registry:
    registry = Registry(settings)
    registry.add(system.server)
    for source_id in SOURCES:
        registry.add(make_source_server(source_id))
    registry.add(portfolio.server)
    registry.add(radar.server)
    registry.add(notify.server)
    registry.add(admin.server)
    registry.add(omni.server)
    return registry


def build_services(settings: Settings) -> dict[str, Any]:
    """Objects tools need at run time, handed to them through ToolContext.services."""
    return {"connectors": build_connectors(settings), "secrets": build_secret_store(settings)}
