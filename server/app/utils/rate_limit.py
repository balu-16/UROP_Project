import time
from collections import defaultdict, deque

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


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

    def check_key(self, key: str) -> bool:
        """Return True when allowed, False when the rate limit is exceeded."""
        self._cleanup_stale()
        now = time.monotonic()
        bucket = self.events[key]
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True


class RateLimitMiddleware:
    """Pure ASGI rate-limiting middleware.

    Deliberately avoids BaseHTTPMiddleware: that wrapper consumes the receive
    channel, which makes `request.is_disconnected()` report True immediately
    inside streaming responses and kills SSE streams before the first token.
    """

    def __init__(
        self,
        app: ASGIApp,
        limiter: InMemoryRateLimiter,
        exempt_paths: set[str] | None = None,
    ):
        self.app = app
        self.limiter = limiter
        self.exempt_paths = exempt_paths or set()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in self.exempt_paths:
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        key = client[0] if client else "unknown"
        if not self.limiter.check_key(key):
            response = JSONResponse(
                status_code=429, content={"detail": "Rate limit exceeded"}
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
