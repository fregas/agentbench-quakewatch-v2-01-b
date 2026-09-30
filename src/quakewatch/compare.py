"""Deterministic one-to-one matching across earthquake catalogues."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import deque
from dataclasses import dataclass

from .models import Event, distance_km


@dataclass(frozen=True)
class Match:
    usgs: Event
    emsc: Event
    time_difference_s: float
    distance_km: float

    @property
    def magnitude_difference(self) -> float | None:
        """Signed USGS minus EMSC magnitude, or None if either is unknown."""
        if self.usgs.magnitude is None or self.emsc.magnitude is None:
            return None
        return self.usgs.magnitude - self.emsc.magnitude


@dataclass(frozen=True)
class Comparison:
    matches: tuple[Match, ...]
    unmatched_usgs: tuple[Event, ...]
    unmatched_emsc: tuple[Event, ...]


def compare_events(events: list[Event]) -> Comparison:
    """Maximum-cardinality matching within inclusive 60-second/50-km bounds.

    Candidate order prefers smaller time difference, then distance, then ID.
    Augmenting paths avoid losing valid pairs to an early greedy assignment.
    This does not minimize the total distance or time difference of all pairs.
    """
    usgs = sorted((e for e in events if e.source == "usgs"), key=lambda e: (e.time, e.id))
    emsc = sorted((e for e in events if e.source == "emsc"), key=lambda e: (e.time, e.id))
    times = [e.time.timestamp() for e in emsc]
    edges: dict[int, list[int]] = {}
    metrics: dict[tuple[int, int], tuple[float, float]] = {}
    for i, event in enumerate(usgs):
        timestamp = event.time.timestamp()
        candidates: list[tuple[float, float, str, int]] = []
        for j in range(bisect_left(times, timestamp - 60), bisect_right(times, timestamp + 60)):
            other = emsc[j]
            distance = distance_km(event.lat, event.lon, other.lat, other.lon)
            if distance <= 50:
                delta = abs((event.time - other.time).total_seconds())
                candidates.append((delta, distance, other.id, j))
                metrics[i, j] = delta, distance
        edges[i] = [j for _, _, _, j in sorted(candidates)]

    left: dict[int, int] = {}
    right: dict[int, int] = {}
    for root in range(len(usgs)):
        queue = deque([root])
        parents: dict[int, int] = {}
        visited = {root}
        endpoint: int | None = None
        while queue and endpoint is None:
            i = queue.popleft()
            for j in edges[i]:
                if j in parents:
                    continue
                parents[j] = i
                if j not in right:
                    endpoint = j
                    break
                owner = right[j]
                if owner not in visited:
                    visited.add(owner)
                    queue.append(owner)
        while endpoint is not None:
            i = parents[endpoint]
            previous = left.get(i)
            left[i] = endpoint
            right[endpoint] = i
            endpoint = previous

    return Comparison(
        matches=tuple(Match(usgs[i], emsc[j], *metrics[i, j]) for i, j in sorted(left.items())),
        unmatched_usgs=tuple(e for i, e in enumerate(usgs) if i not in left),
        unmatched_emsc=tuple(e for j, e in enumerate(emsc) if j not in right),
    )
