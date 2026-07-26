"""Simple job runner protocol with in-process implementation."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

logger = logging.getLogger(__name__)

JobFunc = Callable[..., Awaitable[Any] | Any]


class JobRunner(Protocol):
    def enqueue(self, name: str, func: JobFunc, *args: Any, **kwargs: Any) -> str: ...


class InProcessJobRunner:
    """Runs jobs in background threads/event loops — fine for v0.1."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._counter = 0
        self._lock = threading.Lock()

    def enqueue(self, name: str, func: JobFunc, *args: Any, **kwargs: Any) -> str:
        with self._lock:
            self._counter += 1
            job_id = f"{name}-{self._counter}"
            self._jobs[job_id] = {"name": name, "status": "queued"}

        def _target() -> None:
            self._jobs[job_id]["status"] = "running"
            try:
                result = func(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    asyncio.run(result)
                self._jobs[job_id]["status"] = "done"
            except Exception as exc:  # noqa: BLE001
                logger.exception("job %s failed", job_id)
                self._jobs[job_id]["status"] = "failed"
                self._jobs[job_id]["error"] = str(exc)

        t = threading.Thread(target=_target, name=job_id, daemon=True)
        t.start()
        return job_id

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self._jobs.get(job_id)


_runner: InProcessJobRunner | None = None


def get_job_runner() -> InProcessJobRunner:
    global _runner
    if _runner is None:
        _runner = InProcessJobRunner()
    return _runner
