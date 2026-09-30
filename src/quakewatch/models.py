"""Shared event model and geographic filtering."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Literal

Source = Literal["usgs", "emsc"]
Window = Literal["hour", "day", "week"]
WINDOW_SECONDS: dict[Window, int] = {"hour": 3600, "day": 86400, "week": 604800}


class QuakewatchError(Exception):
    """A source or cache operation could not be completed."""


@dataclass(frozen=True)
class Event:
    id: str
    time: datetime
    magnitude: float | None
    depth_km: float | None
    lat: float
    lon: float
    place: str
    source: Source

    def __post_init__(self) -> None:
        if self.time.tzinfo is None or self.time.utcoffset() is None:
            raise ValueError("Event time must be timezone-aware")
        object.__setattr__(self, "time", self.time.astimezone(timezone.utc))
        if not (-90 <= self.lat <= 90 and -180 <= self.lon <= 180):
            raise ValueError("Invalid event coordinates")
        for value in (self.magnitude, self.depth_km):
            if value is not None and not math.isfinite(value):
                raise ValueError("Magnitude and depth must be finite")

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = asdict(self)
        result["time"] = self.time.isoformat().replace("+00:00", "Z")
        return result


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle surface distance using the mean Earth radius."""
    a, b = math.radians(lat1), math.radians(lat2)
    h = (
        math.sin((b - a) / 2) ** 2
        + math.cos(a) * math.cos(b) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, h))))


def filter_events(
    events: list[Event],
    *,
    start: datetime,
    end: datetime,
    min_mag: float | None = None,
    near: tuple[float, float] | None = None,
    radius_km: float | None = None,
) -> list[Event]:
    if (near is None) != (radius_km is None):
        raise ValueError("--near and --radius-km must be provided together")
    if radius_km is not None and (not math.isfinite(radius_km) or radius_km < 0):
        raise ValueError("Radius must be finite and nonnegative")
    if near is not None and not (-90 <= near[0] <= 90 and -180 <= near[1] <= 180):
        raise ValueError("Invalid center coordinates")
    if min_mag is not None and not math.isfinite(min_mag):
        raise ValueError("Minimum magnitude must be finite")
    return sorted(
        (
            e
            for e in events
            if start <= e.time <= end
            and (min_mag is None or (e.magnitude is not None and e.magnitude >= min_mag))
            and (near is None or radius_km is None or distance_km(*near, e.lat, e.lon) <= radius_km)
        ),
        key=lambda e: (e.time, e.source, e.id),
        reverse=True,
    )
