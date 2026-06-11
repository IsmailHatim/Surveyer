"""Forward structlog events to a callback for the duration of a run."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

import structlog


@contextmanager
def forward_logs(callback: Callable[[str], None]) -> Iterator[None]:
    """Route every structlog event to callback as a formatted line."""
    previous = structlog.get_config()

    def _emit(_logger, _method_name, event_dict):
        event = event_dict.pop("event", "")
        kv = " ".join(f"{k}={v}" for k, v in event_dict.items())
        callback(f"{event} {kv}".strip())
        raise structlog.DropEvent

    structlog.configure(processors=[_emit])
    try:
        yield
    finally:
        structlog.configure(**previous)
