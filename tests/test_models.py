from dataclasses import replace
from datetime import timedelta, timezone

import pytest

from quakewatch import distance_km, filter_events


def test_event_utc_and_serialization(event):
    shifted = replace(event, time=event.time.astimezone(timezone(timedelta(hours=5))))
    assert shifted.time == event.time
    assert shifted.time.utcoffset() == timedelta(0)
    assert shifted.as_dict()["time"] == "2026-09-30T12:00:00Z"
    with pytest.raises(ValueError, match="timezone"):
        replace(event, time=event.time.replace(tzinfo=None))
    for attrs in (
        {"lat": 91},
        {"lon": -181},
        {"lat": float("nan")},
        {"magnitude": float("inf")},
        {"depth_km": float("nan")},
    ):
        with pytest.raises(ValueError):
            replace(event, **attrs)


def test_distance():
    assert distance_km(0, 0, 0, 0) == 0
    assert distance_km(0, 0, 0, 1) == pytest.approx(111.195, abs=0.001)
    assert distance_km(0, 179.9, 0, -179.9) == pytest.approx(22.239, abs=0.001)
    assert distance_km(90, 0, -90, 180) == pytest.approx(20015.114, abs=0.001)


def test_filters(event):
    start, end = event.time - timedelta(hours=1), event.time
    events = [
        event,
        replace(event, id="old", time=start - timedelta(seconds=1)),
        replace(event, id="future", time=end + timedelta(seconds=1)),
        replace(event, id="unknown", magnitude=None),
        replace(event, id="far", lon=10),
    ]
    assert len(filter_events(events, start=start, end=end)) == 3
    assert filter_events(events, start=start, end=end, min_mag=4.5, near=(0, 0), radius_km=50) == [
        event
    ]
    assert filter_events(events, start=start, end=end, min_mag=5) == []
    for kwargs in (
        {"near": (0, 0)},
        {"radius_km": 5},
        {"near": (0, 0), "radius_km": -1},
        {"near": (100, 0), "radius_km": 1},
        {"near": (0, 0), "radius_km": float("nan")},
        {"min_mag": float("inf")},
    ):
        with pytest.raises(ValueError):
            filter_events(events, start=start, end=end, **kwargs)
