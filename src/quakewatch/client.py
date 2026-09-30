"""Fetch and normalize USGS GeoJSON and EMSC FDSN JSON."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Any, Literal, cast

import httpx

from .cache import ResponseCache
from .models import WINDOW_SECONDS, Event, QuakewatchError, Source, Window, filter_events

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_{window}.geojson"
EMSC_URL = "https://www.seismicportal.eu/fdsnws/event/1/query"
PAGE_SIZE = 20000


def parse_events(data: dict[str, Any], source: Source) -> list[Event]:
    events: list[Event] = []
    try:
        if data["type"] != "FeatureCollection" or not isinstance(data["features"], list):
            raise ValueError("Expected a FeatureCollection")
        for feature in data["features"]:
            p = feature["properties"]
            lon, lat, depth = feature["geometry"]["coordinates"]
            if source == "usgs":
                when = datetime.fromtimestamp(float(p["time"]) / 1000, tz=timezone.utc)
                place = p.get("place") or "Unknown"
            else:
                when = datetime.fromisoformat(p["time"].replace("Z", "+00:00"))
                # FDSN times without a suffix are UTC by specification.
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                depth = p["depth"]
                place = p.get("flynn_region") or "Unknown"
            events.append(
                Event(
                    id=str(feature["id"]),
                    time=when,
                    magnitude=None if p.get("mag") is None else float(p["mag"]),
                    depth_km=None if depth is None else float(depth),
                    lat=float(lat),
                    lon=float(lon),
                    place=str(place),
                    source=source,
                )
            )
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as exc:
        raise QuakewatchError(f"Invalid {source.upper()} response: {exc}") from exc
    return events


class QuakeClient:
    """Library client. Inject an httpx client for custom transport or testing."""

    def __init__(
        self, cache: ResponseCache | None = None, http: httpx.Client | None = None
    ) -> None:
        self.cache = cache if cache is not None else ResponseCache()
        self._http = http

    def _request(self, url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            if self._http is not None:
                response = self._http.get(url, params=params)
            else:
                with httpx.Client(
                    timeout=30,
                    follow_redirects=True,
                    transport=httpx.HTTPTransport(retries=2),
                    headers={"User-Agent": "quakewatch/0.1.0"},
                ) as client:
                    response = client.get(url, params=params)
            response.raise_for_status()
            if response.status_code == 204:
                return {"type": "FeatureCollection", "features": []}
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            return cast(dict[str, Any], data)
        except (httpx.HTTPError, ValueError) as exc:
            raise QuakewatchError(f"Request failed for {url}: {exc}") from exc

    def _fetch(self, source: Source, window: Window, now: datetime) -> dict[str, Any]:
        if source == "usgs":
            data = self._request(USGS_URL.format(window=window))
            parse_events(data, source)  # Do not cache malformed responses.
            return data
        params = {
            "format": "json",
            "starttime": (now - timedelta(seconds=WINDOW_SECONDS[window])).isoformat(),
            "endtime": now.isoformat(),
            "limit": str(PAGE_SIZE),
            "offset": "1",
            "orderby": "time",
        }
        features: list[Any] = []
        while True:
            page = self._request(EMSC_URL, params)
            parse_events(page, source)
            batch = page["features"]
            features.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
            params["offset"] = str(len(features) + 1)
        return {"type": "FeatureCollection", "features": features}

    def events(
        self,
        *,
        window: Window = "day",
        source: Literal["usgs", "emsc", "both"] = "both",
        min_mag: float | None = None,
        near: tuple[float, float] | None = None,
        radius_km: float | None = None,
        now: datetime | None = None,
    ) -> list[Event]:
        if window not in WINDOW_SECONDS or source not in ("usgs", "emsc", "both"):
            raise ValueError("Invalid window or source")
        now = now if now is not None else datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        now = now.astimezone(timezone.utc)
        start = now - timedelta(seconds=WINDOW_SECONDS[window])
        # Validate filters before any network request.
        filter_events([], start=start, end=now, min_mag=min_mag, near=near, radius_km=radius_km)
        sources: tuple[Source, ...] = ("usgs", "emsc") if source == "both" else (source,)
        events: list[Event] = []
        for name in sources:
            # A stable window key reuses responses even though FDSN query times change.
            data = self.cache.get(f"v1:{name}:{window}", partial(self._fetch, name, window, now))
            events.extend(parse_events(data, name))
        return filter_events(
            events, start=start, end=now, min_mag=min_mag, near=near, radius_km=radius_km
        )
