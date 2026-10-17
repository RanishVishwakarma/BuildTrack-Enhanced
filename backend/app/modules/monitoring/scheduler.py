"""Periodic runner for monitoring, voice-call dispatch and similar jobs.

Started from the FastAPI lifespan. It does not depend on any page being open.
State (alerts, job runs, queued calls) is in MongoDB, so a restart simply
continues on the next tick; the lease in engine.acquire_lock prevents two
instances from running the job at the same time.
"""

import asyncio
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)
_task: asyncio.Task | None = None


async def _loop(db) -> None:
    from app.modules.monitoring.engine import run_monitoring
    from app.modules.voice.service import dispatch_due_calls

    await asyncio.sleep(10)  # let the app finish starting
    while True:
        try:
            await run_monitoring(db, trigger="schedule")
        except Exception:
            logger.exception("Scheduled monitoring run failed")
        try:
            await dispatch_due_calls(db)
        except Exception:
            logger.exception("Voice call dispatch failed")
        await asyncio.sleep(max(1, settings.monitoring_interval_minutes) * 60)


def start(db) -> None:
    global _task
    if settings.monitoring_enabled and _task is None:
        _task = asyncio.create_task(_loop(db))
        logger.info("Monitoring scheduler started (every %s min)", settings.monitoring_interval_minutes)


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
