"""Shared outbound HTTP client: robots.txt, rate limiting, caching and logging.

Used by both the recommendation search and the listing fetch services. Design
goals (from the brief):
  * Respect robots.txt and site terms.
  * Rate-limit and cache so we never hammer an external site.
  * Log every external request and any error.
  * Make it easy to swap in a future API or CSV import.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from pplate.config import get_settings
from pplate.models import ExternalRequestLog

logger = logging.getLogger("pplate.http")


def _cache_key(method: str, url: str, params: dict | None) -> str:
    raw = json.dumps({"m": method, "u": url, "p": params or {}}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class _RateLimiter:
    """Simple per-host minimum-interval limiter (in-process)."""

    def __init__(self, min_interval_seconds: float) -> None:
        self.min_interval = max(0.0, min_interval_seconds)
        self._last: dict[str, float] = {}

    def wait(self, host: str) -> None:
        if self.min_interval <= 0:
            return
        last = self._last.get(host, 0.0)
        elapsed = time.monotonic() - last
        remaining = self.min_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last[host] = time.monotonic()


@dataclass
class FetchResult:
    url: str
    status_code: int | None
    text: str | None
    cached: bool
    allowed_by_robots: bool | None
    error: str | None = None


class ExternalClient:
    """httpx wrapper adding robots checks, caching, rate limiting and DB logging."""

    def __init__(
        self,
        db: Session | None = None,
        *,
        rate_limit_seconds: float | None = None,
        cache_ttl_seconds: int | None = None,
        user_agent: str | None = None,
        timeout: float | None = None,
        cache_dir: str | None = None,
    ) -> None:
        settings = get_settings()
        self.db = db
        self.rate_limit_seconds = (
            settings.search_rate_limit_seconds if rate_limit_seconds is None else rate_limit_seconds
        )
        self.cache_ttl_seconds = (
            settings.search_cache_ttl_seconds if cache_ttl_seconds is None else cache_ttl_seconds
        )
        self.user_agent = user_agent or settings.search_user_agent
        self.timeout = timeout or settings.external_request_timeout_seconds
        self.cache_dir = Path(cache_dir or settings.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._limiter = _RateLimiter(self.rate_limit_seconds)
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    # -- robots ------------------------------------------------------------
    def allowed(self, url: str) -> bool | None:
        """Return True/False if robots.txt is readable, None if unknown."""
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return None
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            parser = urllib.robotparser.RobotFileParser()
            robots_url = f"{origin}/robots.txt"
            try:
                self._limiter.wait(parsed.netloc)
                resp = httpx.get(
                    robots_url,
                    headers={"User-Agent": self.user_agent},
                    timeout=self.timeout,
                    follow_redirects=True,
                )
                if resp.status_code == 200:
                    parser.parse(resp.text.splitlines())
                    self._robots[origin] = parser
                else:
                    # No robots.txt -> nothing disallowed by it.
                    self._robots[origin] = None
            except Exception as exc:  # noqa: BLE001 - best effort
                logger.warning("robots.txt fetch failed for %s: %s", origin, exc)
                self._robots[origin] = None
        parser = self._robots[origin]
        if parser is None:
            return None
        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception:  # noqa: BLE001
            return None

    # -- cache -------------------------------------------------------------
    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _cache_read(self, key: str) -> str | None:
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        if time.time() - payload.get("saved_at", 0) > self.cache_ttl_seconds:
            return None
        return payload.get("text")

    def _cache_write(self, key: str, text: str) -> None:
        try:
            self._cache_path(key).write_text(json.dumps({"saved_at": time.time(), "text": text}))
        except OSError as exc:  # pragma: no cover
            logger.warning("cache write failed: %s", exc)

    # -- logging -----------------------------------------------------------
    def _log(
        self,
        *,
        provider: str,
        method: str,
        url: str,
        status_code: int | None,
        cached: bool,
        allowed_by_robots: bool | None,
        error: str | None,
    ) -> None:
        logger.info(
            "[%s] %s %s -> %s (cached=%s, robots=%s, error=%s)",
            provider,
            method,
            url,
            status_code,
            cached,
            allowed_by_robots,
            error,
        )
        if self.db is None:
            return
        try:
            self.db.add(
                ExternalRequestLog(
                    provider=provider,
                    method=method,
                    url=url[:800],
                    status_code=status_code,
                    cached=cached,
                    allowed_by_robots=allowed_by_robots,
                    error=error,
                )
            )
            self.db.commit()
        except Exception as exc:  # noqa: BLE001 - never fail a request over logging
            logger.debug("external request log failed: %s", exc)
            self.db.rollback()

    # -- fetch -------------------------------------------------------------
    def get(
        self,
        url: str,
        *,
        provider: str = "generic",
        params: dict | None = None,
        headers: dict | None = None,
        respect_robots: bool = True,
        use_cache: bool = True,
    ) -> FetchResult:
        allowed = self.allowed(url) if respect_robots else None
        if respect_robots and allowed is False:
            self._log(
                provider=provider,
                method="GET",
                url=url,
                status_code=None,
                cached=False,
                allowed_by_robots=False,
                error="blocked by robots.txt",
            )
            return FetchResult(
                url=url,
                status_code=None,
                text=None,
                cached=False,
                allowed_by_robots=False,
                error="blocked by robots.txt",
            )

        key = _cache_key("GET", url, params)
        if use_cache:
            cached_text = self._cache_read(key)
            if cached_text is not None:
                self._log(
                    provider=provider,
                    method="GET",
                    url=url,
                    status_code=200,
                    cached=True,
                    allowed_by_robots=allowed,
                    error=None,
                )
                return FetchResult(url, 200, cached_text, True, allowed)

        host = urlparse(url).netloc
        self._limiter.wait(host)
        try:
            resp = httpx.get(
                url,
                params=params,
                headers={"User-Agent": self.user_agent, **(headers or {})},
                timeout=self.timeout,
                follow_redirects=True,
            )
            text = resp.text
            if use_cache and resp.status_code == 200:
                self._cache_write(key, text)
            self._log(
                provider=provider,
                method="GET",
                url=url,
                status_code=resp.status_code,
                cached=False,
                allowed_by_robots=allowed,
                error=None,
            )
            return FetchResult(url, resp.status_code, text, False, allowed)
        except Exception as exc:  # noqa: BLE001 - surface as a logged error
            self._log(
                provider=provider,
                method="GET",
                url=url,
                status_code=None,
                cached=False,
                allowed_by_robots=allowed,
                error=str(exc),
            )
            return FetchResult(url, None, None, False, allowed, error=str(exc))

    def get_json(self, url: str, **kwargs) -> tuple[dict | list | None, FetchResult]:
        result = self.get(url, **kwargs)
        if not result.text:
            return None, result
        try:
            return json.loads(result.text), result
        except json.JSONDecodeError as exc:
            result.error = f"invalid JSON: {exc}"
            return None, result
