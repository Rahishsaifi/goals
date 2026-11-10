from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock


@dataclass
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int = 0


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = timedelta(seconds=window_seconds)
        self._hits: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> RateLimitResult:
        now = datetime.now(UTC)
        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > self.window:
                bucket.popleft()
            if len(bucket) >= self.limit:
                oldest = bucket[0]
                retry = int((self.window - (now - oldest)).total_seconds()) + 1
                return RateLimitResult(allowed=False, retry_after_seconds=max(retry, 1))
            bucket.append(now)
            return RateLimitResult(allowed=True)

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()
