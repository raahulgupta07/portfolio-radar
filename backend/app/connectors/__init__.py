"""Connector library: one read-only connector per source tracker."""

from app.connectors.base import Connector
from app.connectors.mock import MockConnector
from app.secretstore import SecretStore
from app.settings import Settings

SOURCES = {
    "jira": ("JIRA", "Digital Teams"),
    "openproject": ("OpenProject", "Data Team"),
    "multica": ("Multica", "AI and Agent Teams"),
}


def build_connectors(settings: Settings, store: SecretStore) -> dict[str, Connector]:
    """Mock: the sample data. Live: each source as set up in Admin → Connections (address, token, field mapping)."""
    if settings.source_mode == "mock":
        return {sid: MockConnector(sid, settings.sample_data_path) for sid in SOURCES}
    from app.connectors.live import LiveConnector

    return {sid: LiveConnector(sid, name, settings, store) for sid, (name, _) in SOURCES.items()}
