"""Load and save the provenance ledger as JSON."""

from __future__ import annotations

from pathlib import Path

import msgspec

from surveyer.models import Ledger


def save_ledger(ledger: Ledger, path: str | Path) -> None:
    """Serialise ledger to JSON at path."""
    Path(path).write_bytes(msgspec.json.encode(ledger))


def load_ledger(path: str | Path) -> Ledger:
    """Deserialise a ledger previously written."""
    return msgspec.json.decode(Path(path).read_bytes(), type=Ledger)
