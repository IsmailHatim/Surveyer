from __future__ import annotations

import threading

import pytest

from surveyer.cancel import PipelineCancelled, check_cancelled


def test_check_cancelled_none_is_noop():
    check_cancelled(None)  # must not raise


def test_check_cancelled_unset_event_is_noop():
    check_cancelled(threading.Event())  # not set: no raise


def test_check_cancelled_set_event_raises():
    event = threading.Event()
    event.set()
    with pytest.raises(PipelineCancelled):
        check_cancelled(event)
