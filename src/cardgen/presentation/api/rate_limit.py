"""Примитивный in-memory rate limit для одного процесса.

Для одного контейнера этого достаточно как защита от случайного шквала
запросов. В multi-instance продакшене лимит нужно вынести в Redis.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from collections.abc import Callable


class RateLimiter:
    def __init__(
        self,
        limit: int,
        window_s: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, key: str) -> tuple[bool, int | None]:
        """Возвращает (разрешено, секунды до следующей попытки)."""
        if self.limit <= 0:
            return True, None

        now = self._clock()
        async with self._lock:
            bucket = self._hits.setdefault(key, deque())
            cutoff = now - self.window_s
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                retry_after = max(1, math.ceil(bucket[0] + self.window_s - now))
                return False, retry_after
            bucket.append(now)
            if len(self._hits) > 2048:
                stale = [
                    key for key, values in self._hits.items() if not values or values[-1] <= cutoff
                ]
                for key in stale:
                    self._hits.pop(key, None)
            return True, None
