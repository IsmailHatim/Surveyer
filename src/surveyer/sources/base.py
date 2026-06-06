"""Source protocol and a shared caching/retrying HTTP client."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Protocol

import httpx
import structlog

from surveyer.models import Record

log = structlog.get_logger()


class Source(Protocol):
    """A bibliographic source adapter."""

    name: str

    def search(self, terms: str, *, max_results: int) -> list[Record]:
        """Return raw records (provenance fields filled by the caller)."""
        ...


class HttpClient:
    """GET JSON client with caching, rate limiting, and retries."""

    def __init__(
        self,
        *,
        cache_dir: str | Path,
        transport: httpx.BaseTransport | None = None,
        min_interval: float = 0.0,
        max_retries: int = 4,
        backoff: float = 1.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Initialise the client with cache directory and retry settings."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.Client(
            transport=transport, timeout=30.0, headers=headers or {}
        )
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.backoff = backoff
        self._last_call = 0.0

    def _cache_path(self, url: str, params: dict) -> Path:
        key = json.dumps({"url": url, "params": params}, sort_keys=True)
        digest = hashlib.sha256(key.encode()).hexdigest()[:32]
        return self.cache_dir / f"{digest}.json"

    def get_json(self, url: str, *, params: dict) -> dict:
        """Fetch JSON from url with caching, rate limiting, and retries."""
        cache = self._cache_path(url, params)
        if cache.exists():
            return json.loads(cache.read_text())

        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                resp = self._client.get(url, params=params)
            except httpx.TransportError as exc:
                log.warning(
                    "http.transport_error", url=url, attempt=attempt, error=str(exc)
                )
                if attempt < self.max_retries:
                    time.sleep(self.backoff * attempt)
                    continue
                raise
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = self.backoff * attempt
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = float(retry_after)
                log.warning(
                    "http.retry", url=url, status=resp.status_code, attempt=attempt
                )
                if attempt < self.max_retries:
                    time.sleep(wait)
                    continue
            resp.raise_for_status()
            data = resp.json()
            cache.write_text(json.dumps(data))
            return data
        raise RuntimeError(f"GET failed after {self.max_retries} attempts: {url}")

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.monotonic()
