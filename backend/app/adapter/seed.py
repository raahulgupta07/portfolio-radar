"""First-run set-up: the three sources and the approved prefix list.
Safe to run again: it adds what is missing and changes nothing else."""

from sqlalchemy import select

from app.connectors import SOURCES
from app.db import session_scope
from app.models.app import Prefix, Source

DEFAULT_PREFIXES = {
    "CHL-DP-": "City Holdings Digital Programme",
    "CHL-IT-": "City Holdings IT",
    "CHL-IT-DAAI-": "City Holdings IT Data, Analytics and AI",
    "CMHL-IT-": "City Mart Holdings IT",
}


async def seed() -> dict[str, int]:
    added = {"sources": 0, "prefixes": 0}
    async with session_scope() as session:
        have = {s.id for s in (await session.scalars(select(Source))).all()}
        for sid, (name, team) in SOURCES.items():
            if sid not in have:
                session.add(Source(id=sid, type=sid, name=name, team=team, secret_ref=f"{sid}-read-token"))
                added["sources"] += 1
        have_p = {p.value for p in (await session.scalars(select(Prefix))).all()}
        for value, desc in DEFAULT_PREFIXES.items():
            if value not in have_p:
                session.add(Prefix(value=value, description=desc, active=True))
                added["prefixes"] += 1
    return added
