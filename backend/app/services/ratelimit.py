"""Tiny in-memory fixed-window rate limiter (per process).

Good enough for a single-process local/self-hosted deployment; if you ever run
multiple workers behind a load balancer, move the counters to shared storage.
"""
from __future__ import annotations

import time
from collections import defaultdict

_buckets: dict[str, list[float]] = {}


def allow(key: str, limit: int, window_seconds: float) -> bool:
    """True when `key` may proceed (under `limit` hits per window)."""
    now = time.monotonic()
    hits = [t for t in _buckets.get(key, ()) if now - t < window_seconds]
    allowed = len(hits) < limit
    if allowed:
        hits.append(now)
    _buckets[key] = hits
    return allowed


def reset(key: str) -> None:
    _buckets.pop(key, None)
