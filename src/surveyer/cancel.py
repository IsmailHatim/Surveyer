"""Cooperative cancellation for long-running pipeline stages."""

from __future__ import annotations

import threading


class PipelineCancelled(Exception):  # noqa: N818
    """Raised when a cooperative cancel Event is set mid-run."""


def check_cancelled(cancel: threading.Event | None) -> None:
    """Raise PipelineCancelled if the cancel event is set."""
    if cancel is not None and cancel.is_set():
        raise PipelineCancelled
