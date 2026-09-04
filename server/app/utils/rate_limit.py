import time
from collections import defaultdict, deque

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


_TRUSTED_PROXY_NETWORKS = ("127.", "::1", "10.", "172.16.", "172.17.", "172.18.", "192.168.")


def _is_trusted_proxy_peer(client_ip: str | None) -> bool:
    if not client_ip:
        return False
    return client_ip.startswith(_TRUSTED_PROXY_NETWORKS)


def _normalize_path(path: str | None) -> str:
    if not path:
        return "/"
    if len(path) > 1 and path.endswith("/"):
        return path[:-1]
    return path


class InMemoryRateLimiter:
    def __init__(
        self,
        limit_per_minute: int,
        per_route_limits: dict[str, int] | None = None,
    ):
        self.limit = limit_per_minute
        self.per_route_limits = dict(per_route_limits or {})
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

    def limit_for(self, path: str) -> int:
        for prefix, limit in self.per_route_limits.items():
            if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
                return limit
        return self.limit

    def check_key(self, key: str, path: str = "/") -> bool:
        """Return True when allowed, False when the rate limit is exceeded."""
        self._cleanup_stale()
        now = time.monotonic()
        bucket_key = f"{key}|{_normalize_path(path)}"
        # Per-route buckets share the limiter but isolate budgets; fall back
        # to the global limit when no prefix matches.
        limit = self.limit_for(_normalize_path(path))
        bucket = self.events[bucket_key]
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
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
        path = _normalize_path(scope.get("path"))
        exempt = {_normalize_path(p) for p in self.exempt_paths}
        if scope["type"] != "http" or path in exempt:
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        direct_ip = client[0] if client else None
        key = direct_ip or "unknown"
        # Behind Caddy/Docker the direct peer is loopback: honor XFF only
        # from trusted proxy peers, otherwise a client could spoof its key.
        if _is_trusted_proxy_peer(direct_ip):
            try:
                headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
                forwarded = headers.get("x-forwarded-for", "")
                if forwarded:
                    first = forwarded.split(",")[0].strip()
                    if first:
                        key = first
            except Exception:
                pass
        if not self.limiter.check_key(key, path):
            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": "60"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
