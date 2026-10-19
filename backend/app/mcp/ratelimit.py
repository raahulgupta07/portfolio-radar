"""Token-bucket rate limit per caller. In-process; a shared store (Redis) can
replace it when the gateway runs as more than one copy."""

import time
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    updated: float
    capacity: float


class RateLimiter:
    def __init__(self, per_minute: int, clock=time.monotonic) -> None:
        self.capacity = float(per_minute)
        self.rate = per_minute / 60.0
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}

    def allow(self, key: str, per_minute: int | None = None) -> bool:
        """`per_minute` overrides the default for this caller (agents set up in Admin)."""
        now = self._clock()
        capacity = float(per_minute) if per_minute else self.capacity
        b = self._buckets.get(key)
        if b is None or b.capacity != capacity:
            b = self._buckets[key] = _Bucket(tokens=capacity, updated=now, capacity=capacity)
        b.tokens = min(capacity, b.tokens + (now - b.updated) * capacity / 60.0)
        b.updated = now
        if b.tokens < 1:
            return False
        b.tokens -= 1
        return True
