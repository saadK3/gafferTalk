import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any, TypeVar, cast

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class CacheEntry:
    value: Any
    expires_at: float


class AsyncTtlCache:
    """Small process-local TTL cache with per-key request coalescing."""

    def __init__(self) -> None:
        self._entries: dict[str, CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get_or_load(
        self,
        key: str,
        ttl_seconds: float,
        loader: Callable[[], Awaitable[T]],
    ) -> T:
        cached = self._get(key)
        if cached is not None:
            return cast(T, cached)

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._get(key)
            if cached is not None:
                return cast(T, cached)

            value = await loader()
            self._entries[key] = CacheEntry(
                value=value,
                expires_at=monotonic() + ttl_seconds,
            )
            return value

    def _get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= monotonic():
            self._entries.pop(key, None)
            return None
        return entry.value

    def clear(self) -> None:
        self._entries.clear()
