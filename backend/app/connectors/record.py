"""Record a live tracker's answers for the connector tests.

    python -m app.connectors.record jira --key DAAI --out tests/recorded/jira-cloud.json

Runs inside the gateway container (it uses the address, token and field
mapping saved in Admin). It reads one project the way the nightly sync does,
GET only, and writes every request and answer to the file. Email addresses are
masked; check the file for other names before you commit it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Any

import httpx

from app.connectors import SOURCES
from app.connectors.live import LiveConnector
from app.secretstore import build_secret_store
from app.settings import get_settings

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def _mask(value: Any) -> Any:
    if isinstance(value, str):
        return EMAIL.sub("someone@example.invalid", value)
    if isinstance(value, list):
        return [_mask(v) for v in value]
    if isinstance(value, dict):
        return {k: _mask(v) for k, v in value.items() if k not in {"avatarUrls", "self"}}
    return value


class Recorder(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.inner = httpx.AsyncHTTPTransport()
        self.entries: list[dict[str, Any]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self.inner.handle_async_request(request)
        body = await response.aread()
        try:
            data = json.loads(body)
        except ValueError:
            data = None
        self.entries.append({"path": request.url.path, "params": dict(request.url.params),
                             "status": response.status_code, "json": _mask(data)})
        return httpx.Response(response.status_code, headers=response.headers, content=body)


async def record(source_id: str, key: str, out: Path) -> int:
    settings = get_settings()
    rec = Recorder()
    live = LiveConnector(source_id, SOURCES[source_id][0], settings, build_secret_store(settings), transport=rec)
    await live.list_projects()
    for method in ("get_project", "get_milestones", "get_sprints", "get_task_counts"):
        await getattr(live, method)(key)
    await live.get_links()
    await live.get_risks()
    await live.aclose()
    out.write_text(json.dumps({"base_url": "https://tracker.example.invalid", "requests": rec.entries}, indent=1) + "\n")
    return len(rec.entries)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("source", choices=["jira", "openproject"])
    p.add_argument("--key", required=True, help="One project to read, e.g. DAAI or cdp")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    n = asyncio.run(record(a.source, a.key, a.out))
    print(f"Recorded {n} requests to {a.out}. Check it for names before committing.")


if __name__ == "__main__":
    main()
