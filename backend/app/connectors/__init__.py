"""Connector library: one read-only connector per source tracker."""

from app.connectors.base import Connector
from app.connectors.mock import MockConnector
from app.settings import Settings

SOURCES = {
    "jira": ("JIRA", "Digital Teams"),
    "openproject": ("OpenProject", "Data Team"),
    "multica": ("Multica", "AI and Agent Teams"),
}


def build_connectors(settings: Settings) -> dict[str, Connector]:
    if settings.source_mode == "mock":
        return {sid: MockConnector(sid, settings.sample_data_path) for sid in SOURCES}
    raise RuntimeError(
        "SOURCE_MODE=live is not available yet. Live JIRA and OpenProject connectors are built once "
        "API access is confirmed (see docs/progress.md, Phase 2). Use SOURCE_MODE=mock.")
