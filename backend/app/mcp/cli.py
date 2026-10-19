"""Owner actions on the registry, until the Admin page exists (Phase 4).

    python -m app.mcp.cli tools                       list every tool and its status
    python -m app.mcp.cli on  jira.list_projects --by "Name"
    python -m app.mcp.cli off jira.list_projects --by "Name"
    python -m app.mcp.cli changes                     list changes waiting for review
    python -m app.mcp.cli approve 3 --by "Name"
    python -m app.mcp.cli reject 3 --by "Name"
    python -m app.mcp.cli calls [--limit 20]          latest audit rows
"""

import argparse
import asyncio
import json

from sqlalchemy import select

from app.db import session_scope
from app.mcp.servers import build_registry
from app.models.mcp import McpCall, McpTool, McpToolChange
from app.settings import get_settings


def _split(key: str) -> tuple[str, str]:
    server, _, tool = key.partition(".")
    if not server or not tool:
        raise SystemExit("Use server.tool, for example jira.list_projects")
    return server, tool


async def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m app.mcp.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tools")
    for name in ("on", "off"):
        s = sub.add_parser(name)
        s.add_argument("tool")
        s.add_argument("--by", required=True)
    sub.add_parser("changes")
    for name in ("approve", "reject"):
        s = sub.add_parser(name)
        s.add_argument("change_id", type=int)
        s.add_argument("--by", required=True)
    s = sub.add_parser("calls")
    s.add_argument("--limit", type=int, default=20)
    args = p.parse_args(argv)

    registry = build_registry(get_settings())
    async with session_scope() as session:
        await registry.sync(session)

        if args.cmd == "tools":
            rows = (await session.scalars(select(McpTool).order_by(McpTool.server, McpTool.name))).all()
            for r in rows:
                in_code = "" if registry.get(r.server, r.name) else "  (not in code)"
                print(f"{r.status:<7} {r.server + '.' + r.name:<34} callers={','.join(r.callers):<22} "
                      f"roles={','.join(r.roles) or 'any'}{in_code}")
        elif args.cmd in ("on", "off"):
            server, tool = _split(args.tool)
            await registry.set_status(session, server, tool, args.cmd, args.by)
            print(f"{args.tool} is now {args.cmd.upper()}")
        elif args.cmd == "changes":
            rows = (await session.scalars(select(McpToolChange).where(McpToolChange.status == "pending"))).all()
            if not rows:
                print("No changes waiting for review")
            for c in rows:
                tool = await session.get(McpTool, c.tool_id)
                print(f"#{c.id} {tool.server}.{tool.name}")
                print(json.dumps(c.diff, indent=2))
        elif args.cmd in ("approve", "reject"):
            await registry.decide_change(session, args.change_id, args.cmd == "approve", args.by)
            print(f"Change #{args.change_id} {args.cmd}d")
        elif args.cmd == "calls":
            rows = (await session.scalars(select(McpCall).order_by(McpCall.id.desc()).limit(args.limit))).all()
            for c in reversed(rows):
                print(f"{c.at:%Y-%m-%d %H:%M:%S} {c.outcome:<6} {c.caller_kind}:{c.caller_id} "
                      f"{c.server}.{c.tool} {c.duration_ms}ms {c.reason or ''}")


if __name__ == "__main__":
    asyncio.run(main())
