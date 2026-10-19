"""The worker: runs the scheduled jobs. It reaches data only through the MCP
gateway, with its own service tokens.

    python -m app.worker

Jobs (times in settings, Asia/Yangon):
- nightly sync (SYNC_CRON, default 02:00)
More jobs (Radar check, stale check, digest) are added with Radar.
"""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.adapter.readers import McpHttpReader
from app.adapter.sync import sync_all
from app.health import today_in
from app.settings import Settings, get_settings

log = logging.getLogger("worker")


async def run_sync(settings: Settings) -> None:
    async with McpHttpReader(settings.gateway_url, settings.adapter_token) as reader:
        summary = await sync_all(reader, settings, today_in(settings))
    log.info("sync done: %s", summary.as_dict())


def build_scheduler(settings: Settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(run_sync, CronTrigger.from_crontab(settings.sync_cron, timezone=settings.timezone),
                      args=[settings], id="sync", max_instances=1, coalesce=True)
    return scheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    scheduler = build_scheduler(settings)
    scheduler.start()
    for job in scheduler.get_jobs():
        log.info("job %s next run %s", job.id, job.next_run_time)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
