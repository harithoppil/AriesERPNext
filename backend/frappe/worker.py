"""ARQ worker entry point for Frappe background jobs.

Run with::

    python -m frappe.worker

Or programmatically::

    from frappe.worker import create_arq_worker
    asyncio.run(create_arq_worker())

Configuration is read from ``frappe.conf`` (``redis_queue`` or ``redis``
keys).  The worker registers both ``execute_frappe_job`` and
``run_doc_method`` so that all jobs enqueued by
:func:`~frappe.utils.background_jobs.enqueue` and
:func:`~frappe.utils.background_jobs.enqueue_doc` can be processed.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

import frappe

logger = logging.getLogger("frappe.worker")


async def create_arq_worker() -> None:
    """Create and run an ARQ ``Worker`` for Frappe background jobs."""
    try:
        from arq import Worker
        from arq.connections import RedisSettings
    except ImportError as exc:
        logger.error("ARQ is not installed. Install it with: pip install arq")
        raise SystemExit(1) from exc

    from frappe.utils.background_jobs import (
        execute_frappe_job,
        run_doc_method,
        _get_redis_settings,
    )

    redis_settings = _get_redis_settings()

    worker_functions = [execute_frappe_job, run_doc_method]

    worker = Worker(
        redis_settings=redis_settings,
        functions=worker_functions,
        max_jobs=100,
        job_timeout=300,
        keep_result=3600,          # retain results for 1 hour
        poll_delay=1.0,            # seconds between queue polls when idle
        queue_read_limit=100,      # max jobs to fetch per poll
        retry_jobs=True,
        # Allow pickle so Frappe Documents / arbitrary objects round-trip safely.
        serializers=["pickle"],
    )

    # ── graceful shutdown ───────────────────────────────────────────────
    _shutdown_event = asyncio.Event()

    async def _shutdown(signal_num: int) -> None:
        logger.info("Received signal %d – shutting down worker gracefully...", signal_num)
        _shutdown_event.set()
        await worker.close()
        sys.exit(0)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(_shutdown(s)))

    logger.info(
        "Starting ARQ worker (queues: %s, max_jobs=%d, timeout=%ds)",
        [f.__name__ for f in worker_functions],
        worker.max_jobs,
        worker.job_timeout,
    )

    try:
        await worker.run()
    except asyncio.CancelledError:
        logger.info("Worker cancelled.")
        raise
    except Exception:
        logger.exception("Worker crashed.")
        raise
    finally:
        await worker.close()


# ─── CLI entry point ───────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point: ``python -m frappe.worker``."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    # Minimal frappe init so that conf is available.
    frappe.init("")
    try:
        asyncio.run(create_arq_worker())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()
