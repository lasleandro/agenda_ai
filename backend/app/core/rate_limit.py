"""Small in-process sliding-window limiter for write bursts.

A first, per-instance abuse guard for state-changing API calls — not a
substitute for edge rate limiting (a WAF) or the durable, DB-backed login
limiter in ``app.services.auth_security``. Counts are per application
instance and reset on restart, which is acceptable for "stop one client
hammering writes".
"""

import os
import threading
import time
from collections import defaultdict, deque

_WINDOW_SECONDS = int(os.getenv("WRITE_RATE_LIMIT_WINDOW_SECONDS", "60"))
_MAX_WRITES = int(os.getenv("WRITE_RATE_LIMIT_MAX", "120"))
_MAX_TRACKED_KEYS = 10_000


class InProcessRateLimiter:
    def __init__(self, max_events: int, window_seconds: int) -> None:
        self._max = max_events
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            if len(self._hits) > _MAX_TRACKED_KEYS:
                self._hits.clear()
            bucket = self._hits[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self._max:
                return False
            bucket.append(now)
            return True


write_limiter = InProcessRateLimiter(_MAX_WRITES, _WINDOW_SECONDS)
