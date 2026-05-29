import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class InMemoryRateLimiter:
    def __init__(self, limit_per_minute: int):
        self.limit = limit_per_minute
        self.window_seconds = 60.0
        self.events: dict[str, deque[float]] = defaultdict(deque)
        self._last_cleanup: float = time.monotonic()
        self._cleanup_interval: float = 300.0  # clean up every 5 minutes

    def _cleanup_stale(self) -> None:
        now = time.monotonic()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        stale_clients = [
            client
            for client, bucket in self.events.items()
            if not bucket or now - bucket[-1] > self.window_seconds * 2
        ]
        for client in stale_clients:
            del self.events[client]
        self._last_cleanup = now

    async def check(self, request: Request) -> None:
        self._cleanup_stale()
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        bucket = self.events[client]
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()
        if len(bucket) >= self.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )
        bucket.append(now)
