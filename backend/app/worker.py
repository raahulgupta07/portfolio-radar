"""The worker: scheduled and background jobs. It reaches data only through the
MCP gateway, each job with its own token:

- adapter (service):   nightly sync at the admin's sync time (default 02:00)
- radar-job (service): Radar's check right after the sync; Monday stale check
- radar (agent):       answers people's questions, every few seconds
- notifier (service):  sends approved drafts, every minute

    python -m app.worker
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.adapter.readers import McpHttpReader
from app.adapter.sync import sync_all
from app.health import today_in
from app.radar.assistant import answer_pending
from app.radar.job import act_on_answers, run_check
from app.radar.notifier import run_notifier
from app.radar.runtime import with_channels, with_llm
from app.secretstore import build_secret_store
from app.servicetokens import Job, ServiceTokens
from app.settings import Settings, get_settings

log = logging.getLogger("worker")


_tokens: ServiceTokens | None = None


@asynccontextmanager
async def reader(settings: Settings, job: Job) -> AsyncIterator[McpHttpReader]:
    """A gateway session signed in as one job (adapter, radar_job, radar or notifier)."""
    global _tokens
    if _tokens is None:
        _tokens = ServiceTokens(settings)
    async with McpHttpReader(settings.gateway_url, await _tokens.get(job)) as r:
        yield r


async def nightly(settings: Settings) -> None:
    """Sync all sources, then let Radar check every project."""
    async with reader(settings, "adapter") as r:
        summary = await sync_all(r, settings, today_in(settings))
    log.info("sync done: %s", summary.as_dict())
    async with reader(settings, "radar_job") as r:
        rs = await with_llm(r, settings, build_secret_store(settings))
        log.info("radar check: %s", await run_check(r, rs, today_in(settings)))


async def stale_check(settings: Settings) -> None:
    """Monday 09:00: one message listing work with no update for a long time."""
    async with reader(settings, "radar_job") as r:
        found = [f for f in (await r.call("radar", "get_findings"))["findings"] if f["type"] == "stale" and not f["dismissed"]]
        if found:
            body = "Stale work check: no update in the tracker for a while.\n" + "\n".join(f"- {f['text']}" for f in found)
            await r.call("radar", "post_message", {"to": "*", "kind": "radar", "mood": "alert", "body": body,
                                                    "payload": {"evidence": "Source 'last updated' dates"}})


async def loop(name: str, every: float, fn) -> None:
    while True:
        try:
            await fn()
        except Exception:  # noqa: BLE001  a background loop must keep running
            log.exception("%s failed", name)
        await asyncio.sleep(every)


async def schedule_from_admin(scheduler: AsyncIOScheduler, settings: Settings) -> None:
    """Read the sync time from Admin settings (through MCP) and move the nightly job if it changed."""
    async with reader(settings, "radar_job") as r:
        rules = (await r.call("radar", "get_status"))["rules"]
    hh, mm = rules["sync_time"].split(":")
    trigger = CronTrigger(hour=int(hh), minute=int(mm), timezone=rules["timezone"])
    job = scheduler.get_job("nightly")
    if job is None:
        scheduler.add_job(nightly, trigger, args=[settings], id="nightly", max_instances=1, coalesce=True)
    elif str(job.trigger) != str(trigger):
        job.reschedule(trigger)
        log.info("nightly job moved to %s %s", rules["sync_time"], rules["timezone"])


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(stale_check, CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=settings.timezone),
                      args=[settings], id="stale", max_instances=1, coalesce=True)
    scheduler.start()
    store = build_secret_store(settings)

    async def chat() -> None:
        async with reader(settings, "radar") as r:
            await answer_pending(r, await with_llm(r, settings, store), settings.timezone)

    async def answers() -> None:
        async with reader(settings, "radar_job") as r:
            await act_on_answers(r)

    async def notify() -> None:
        async with reader(settings, "notifier") as r:
            await run_notifier(r, await with_channels(r, settings, store))

    await asyncio.gather(
        loop("schedule", 300, lambda: schedule_from_admin(scheduler, settings)),
        loop("chat", 3, chat),
        loop("answers", 10, answers),
        loop("notifier", 60, notify),
    )


if __name__ == "__main__":
    asyncio.run(main())
