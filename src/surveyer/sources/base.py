"""Source protocol and a shared caching/retrying HTTP client."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Protocol

import httpx
import structlog

from surveyer.models import Record

log = structlog.get_logger()


def _parse_retry_after(value: str) -> float | None:
    """Parse a Retry-After header (delta-seconds or HTTP-date) to seconds.

    Returns None if the value is neither a non-negative integer nor a valid
    HTTP-date, so the caller can fall back to exponential backoff.
    """
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


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
        max_backoff: float = 60.0,
        headers: dict[str, str] | None = None,
        follow_redirects: bool = False,
        refresh: bool = False,
    ) -> None:
        """Initialise the client with cache directory and retry settings."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.Client(
            transport=transport,
            timeout=30.0,
            headers=headers or {},
            follow_redirects=follow_redirects,
        )
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.backoff = backoff
        self.max_backoff = max_backoff
        self.refresh = refresh
        self._last_call = 0.0

    def _retry_wait(self, attempt: int, retry_after: str | None = None) -> float:
        """Exponential backoff, capped, with the server's Retry-After winning."""
        if retry_after:
            seconds = _parse_retry_after(retry_after)
            if seconds is not None:
                return seconds
        return min(self.backoff * (2 ** (attempt - 1)), self.max_backoff)

    def _cache_path(
        self,
        url: str,
        params: dict,
        *,
        suffix: str = "json",
        extra: dict | None = None,
    ) -> Path:
        payload: dict = {"url": url, "params": params}
        if extra:
            payload["extra"] = extra
        key = json.dumps(payload, sort_keys=True)
        digest = hashlib.sha256(key.encode()).hexdigest()[:32]
        return self.cache_dir / f"{digest}.{suffix}"

    def get_json(self, url: str, *, params: dict) -> dict:
        """Fetch JSON from url with caching, rate limiting, and retries."""
        cache = self._cache_path(url, params)
        if cache.exists() and not self.refresh:
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
                    time.sleep(self._retry_wait(attempt))
                    continue
                raise
            if resp.status_code == 429 or resp.status_code >= 500:
                log.warning(
                    "http.retry", url=url, status=resp.status_code, attempt=attempt
                )
                if attempt < self.max_retries:
                    time.sleep(
                        self._retry_wait(attempt, resp.headers.get("Retry-After"))
                    )
                    continue
            resp.raise_for_status()
            data = resp.json()
            cache.write_text(json.dumps(data))
            return data
        raise RuntimeError(f"GET failed after {self.max_retries} attempts: {url}")

    def get_text(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> str | None:
        """Fetch a text body (bibtex) with caching, throttling, and retries."""
        params = params or {}
        headers = headers or {}
        cache = self._cache_path(url, params, suffix="txt", extra={"headers": headers})
        if cache.exists() and not self.refresh:
            text = cache.read_text()
            return text or None

        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                resp = self._client.get(url, params=params, headers=headers)
            except httpx.TransportError as exc:
                log.warning(
                    "http.transport_error", url=url, attempt=attempt, error=str(exc)
                )
                if attempt < self.max_retries:
                    time.sleep(self._retry_wait(attempt))
                    continue
                raise
            if resp.status_code == 404:
                cache.write_text("")  # cache the miss so reruns don't refetch
                return None
            if resp.status_code == 429 or resp.status_code >= 500:
                log.warning(
                    "http.retry", url=url, status=resp.status_code, attempt=attempt
                )
                if attempt < self.max_retries:
                    time.sleep(
                        self._retry_wait(attempt, resp.headers.get("Retry-After"))
                    )
                    continue
            resp.raise_for_status()
            cache.write_text(resp.text)
            return resp.text or None
        raise RuntimeError(f"GET failed after {self.max_retries} attempts: {url}")

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.monotonic()
