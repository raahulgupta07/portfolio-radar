"""Adapter commands.

    python -m app.adapter seed                  add sources and prefixes (first run)
    python -m app.adapter sync                  sync now, through the gateway over MCP/HTTP
    python -m app.adapter sync --source jira    one source only
    python -m app.adapter sync --in-process     no running gateway needed (dev); the guard still runs
    python -m app.adapter po-import FILE        load program office data (programs, charters, projects) from a JSON file
    python -m app.adapter demo [--reset]        dev only: sample data with history (see app/adapter/demo.py)
"""

import argparse
import asyncio
import json

from app.adapter.readers import GatewayReader, McpHttpReader
from app.adapter.demo import load_demo
from app.adapter.seed import seed
from app.adapter.sync import sync_all
from app.health import today_in
from app.mcp.guard import Gateway
from app.mcp.identity import TokenResolver
from app.mcp.servers import build_registry, build_services
from app.servicetokens import ServiceTokens
from app.settings import get_settings


async def main() -> None:
    p = argparse.ArgumentParser(prog="python -m app.adapter")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed")
    d = sub.add_parser("demo")
    d.add_argument("--reset", action="store_true", help="empty the portfolio tables first (dev only)")
    po = sub.add_parser("po-import")
    po.add_argument("file")
    s = sub.add_parser("sync")
    s.add_argument("--source")
    s.add_argument("--in-process", action="store_true")
    args = p.parse_args()
    settings = get_settings()

    if args.cmd == "po-import":
        from pathlib import Path

        from app.db import session_scope
        from app.portfolio.programs import import_file

        async with session_scope() as session:
            print(json.dumps(await import_file(session, Path(args.file))))
        return

    if args.cmd == "seed":
        print(json.dumps(await seed()))
        return

    today = today_in(settings)
    if args.cmd == "demo":
        print(json.dumps(await load_demo(settings, today, args.reset), indent=2))
        return
    if args.in_process:
        registry = build_registry(settings)
        gateway = Gateway(registry, settings, build_services(settings))
        caller = TokenResolver(settings).resolve(f"Bearer {settings.adapter_token}")
        summary = await sync_all(GatewayReader(gateway, caller), settings, today, args.source)
    else:
        tokens = ServiceTokens(settings)
        async with McpHttpReader(settings.gateway_url, await tokens.get("adapter")) as reader:
            summary = await sync_all(reader, settings, today, args.source)
        await tokens.aclose()
    print(json.dumps(summary.as_dict(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
