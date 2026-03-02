"""
loremem HTTP transport layer.

Handles:
  - Bearer auth header injection
  - Retry with exponential backoff (3 attempts)
  - Timeout enforcement (5s context, 10s writes)
  - Error classification into loremem exceptions
  - Async variant (AsyncTransport) for async callers

httpx is used for both sync and async. It is the only required dependency.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from loremem.exceptions import (
    AuthError,
    LoreMemError,
    NetworkError,
    RateLimitError,
    ServerError,
)

logger = logging.getLogger("loremem")

_MAX_RETRIES = 3
_BACKOFF_BASE = 0.5   # seconds — 0.5, 1.0, 2.0
_CONTEXT_TIMEOUT = 5.0   # seconds — context must be fast
_WRITE_TIMEOUT = 10.0    # seconds — reporting calls are less time-sensitive


def _classify(response: httpx.Response) -> None:
    """Raise the appropriate exception for a non-2xx response."""
    status = response.status_code
    try:
        detail = response.json().get("detail", response.text)
    except Exception:
        detail = response.text or str(status)

    if status == 401:
        raise AuthError(f"Authentication failed: {detail}")
    if status == 403:
        raise AuthError(f"Forbidden — workspace mismatch: {detail}")
    if status == 429:
        raise RateLimitError(f"Rate limit exceeded: {detail}")
    if status >= 500:
        raise ServerError(f"Lore API error {status}: {detail}")
    raise LoreMemError(f"Unexpected response {status}: {detail}")


def _should_retry(exc: Exception) -> bool:
    """Only retry on network errors and 5xx; not on 4xx."""
    return isinstance(exc, (NetworkError, ServerError, httpx.TransportError))


# ── Sync transport ────────────────────────────────────────────────────────────


class Transport:
    """Synchronous HTTP transport with retry + backoff."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "loremem-python/0.1.0",
        }

    def post(
        self,
        path: str,
        payload: dict[str, Any],
        timeout: float = _WRITE_TIMEOUT,
    ) -> dict[str, Any]:
        """POST with retry. Returns parsed JSON body."""
        url = f"{self._base_url}{path}"
        last_exc: Exception = LoreMemError("Unknown error")

        for attempt in range(_MAX_RETRIES):
            try:
                response = httpx.post(
                    url,
                    json=payload,
                    headers=self._headers,
                    timeout=timeout,
                )
                if response.is_success:
                    return response.json()
                _classify(response)

            except (AuthError, RateLimitError, LoreMemError):
                raise   # non-retryable
            except httpx.TimeoutException as exc:
                last_exc = NetworkError(f"Request timed out: {exc}")
            except httpx.TransportError as exc:
                last_exc = NetworkError(f"Network error: {exc}")
            except ServerError as exc:
                last_exc = exc

            if attempt < _MAX_RETRIES - 1:
                time.sleep(_BACKOFF_BASE * (2 ** attempt))

        raise last_exc

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        timeout: float = _WRITE_TIMEOUT,
    ) -> dict[str, Any]:
        """GET with retry. Returns parsed JSON body."""
        url = f"{self._base_url}{path}"
        last_exc: Exception = LoreMemError("Unknown error")

        for attempt in range(_MAX_RETRIES):
            try:
                response = httpx.get(
                    url,
                    params=params,
                    headers=self._headers,
                    timeout=timeout,
                )
                if response.is_success:
                    return response.json()
                _classify(response)

            except (AuthError, RateLimitError, LoreMemError):
                raise
            except httpx.TimeoutException as exc:
                last_exc = NetworkError(f"Request timed out: {exc}")
            except httpx.TransportError as exc:
                last_exc = NetworkError(f"Network error: {exc}")
            except ServerError as exc:
                last_exc = exc

            if attempt < _MAX_RETRIES - 1:
                time.sleep(_BACKOFF_BASE * (2 ** attempt))

        raise last_exc


# ── Async transport ───────────────────────────────────────────────────────────


class AsyncTransport:
    """Async HTTP transport with retry + backoff. Use with async AI agent frameworks."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "loremem-python/0.1.0",
        }

    async def post(
        self,
        path: str,
        payload: dict[str, Any],
        timeout: float = _WRITE_TIMEOUT,
    ) -> dict[str, Any]:
        import asyncio

        url = f"{self._base_url}{path}"
        last_exc: Exception = LoreMemError("Unknown error")

        async with httpx.AsyncClient(headers=self._headers, timeout=timeout) as client:
            for attempt in range(_MAX_RETRIES):
                try:
                    response = await client.post(url, json=payload)
                    if response.is_success:
                        return response.json()
                    _classify(response)

                except (AuthError, RateLimitError, LoreMemError):
                    raise
                except httpx.TimeoutException as exc:
                    last_exc = NetworkError(f"Request timed out: {exc}")
                except httpx.TransportError as exc:
                    last_exc = NetworkError(f"Network error: {exc}")
                except ServerError as exc:
                    last_exc = exc

                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_BACKOFF_BASE * (2 ** attempt))

        raise last_exc

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        timeout: float = _WRITE_TIMEOUT,
    ) -> dict[str, Any]:
        import asyncio

        url = f"{self._base_url}{path}"
        last_exc: Exception = LoreMemError("Unknown error")

        async with httpx.AsyncClient(headers=self._headers, timeout=timeout) as client:
            for attempt in range(_MAX_RETRIES):
                try:
                    response = await client.get(url, params=params)
                    if response.is_success:
                        return response.json()
                    _classify(response)

                except (AuthError, RateLimitError, LoreMemError):
                    raise
                except httpx.TimeoutException as exc:
                    last_exc = NetworkError(f"Request timed out: {exc}")
                except httpx.TransportError as exc:
                    last_exc = NetworkError(f"Network error: {exc}")
                except ServerError as exc:
                    last_exc = exc

                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_BACKOFF_BASE * (2 ** attempt))

        raise last_exc
