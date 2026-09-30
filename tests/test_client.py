import copy
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from quakewatch import QuakeClient, QuakewatchError, ResponseCache
from quakewatch.client import parse_events


def test_recorded_normalization(fixtures):
    for source in ("usgs", "emsc"):
        events = parse_events(fixtures[source], source)
        assert len(events) == 3
        assert all(e.source == source and e.time.utcoffset() == timedelta(0) for e in events)
        first = fixtures[source]["features"][0]
        assert events[0].lon == first["geometry"]["coordinates"][0]
        assert events[0].depth_km == (
            first["properties"]["depth"]
            if source == "emsc"
            else first["geometry"]["coordinates"][2]
        )
        assert events[0].id == first["id"]
        assert events[0].magnitude == first["properties"]["mag"]
    emsc = copy.deepcopy(fixtures["emsc"])
    emsc["features"][0]["properties"]["time"] = "2026-09-30T12:00:00"
    emsc["features"][0]["properties"]["mag"] = None
    emsc["features"][0]["properties"]["depth"] = None
    emsc["features"][0]["properties"]["flynn_region"] = None
    e = parse_events(emsc, "emsc")[0]
    assert e.magnitude is None and e.depth_km is None and e.place == "Unknown"


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"type": "wrong", "features": []},
        {"type": "FeatureCollection", "features": None},
        {"type": "FeatureCollection", "features": [{}]},
    ],
)
def test_malformed(data):
    with pytest.raises(QuakewatchError, match="Invalid USGS"):
        parse_events(data, "usgs")


def test_http_and_stable_cache(fixtures, tmp_path):
    calls = []
    now = max(e.time for s in ("usgs", "emsc") for e in parse_events(fixtures[s], s)) + timedelta(
        seconds=5
    )

    def handler(request):
        calls.append(request)
        source = "usgs" if request.url.host == "earthquake.usgs.gov" else "emsc"
        return httpx.Response(200, json=fixtures[source])

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = QuakeClient(ResponseCache(tmp_path), http)
        assert len(client.events(now=now)) == 6
        assert len(client.events(now=now + timedelta(seconds=1))) == 6
        assert len(calls) == 2
        assert calls[1].url.params["format"] == "json"
        assert calls[1].url.params["offset"] == "1"
        assert calls[0].url.path.endswith("all_day.geojson")
        assert len(client.events(source="usgs", now=now, min_mag=0)) <= 3


def test_pagination(fixtures, monkeypatch):
    monkeypatch.setattr("quakewatch.client.PAGE_SIZE", 2)
    calls = []

    def handler(request):
        calls.append(request.url.params["offset"])
        start = int(calls[-1]) - 1
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": fixtures["emsc"]["features"][start : start + 2],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = QuakeClient(ResponseCache(enabled=False), http)
        data = client._fetch("emsc", "week", datetime.now(timezone.utc))
    assert len(data["features"]) == 3
    assert calls == ["1", "3"]


@pytest.mark.parametrize("status,payload", [(204, None), (503, None), (200, []), (200, "broken")])
def test_http_errors(status, payload):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: (
                httpx.Response(status, content="not json")
                if payload == "broken"
                else httpx.Response(status, json=payload)
            )
        )
    ) as http:
        client = QuakeClient(ResponseCache(enabled=False), http)
        if status == 204:
            assert client.events(source="usgs") == []
        else:
            with pytest.raises(QuakewatchError, match="Request failed"):
                client.events(source="usgs")


def test_connection_and_default_transport(monkeypatch):
    def fail(request):
        raise httpx.ConnectError("offline", request=request)

    http = httpx.Client(transport=httpx.MockTransport(fail))
    monkeypatch.setattr("quakewatch.client.httpx.Client", lambda **kw: http)
    with pytest.raises(QuakewatchError, match="offline"):
        QuakeClient(ResponseCache(enabled=False)).events(source="emsc")


def test_validation_before_network():
    client = QuakeClient(ResponseCache(enabled=False))
    for kwargs in (
        {"window": "year"},
        {"source": "invalid"},
        {"now": datetime(2026, 1, 1)},
        {"near": (0, 0)},
    ):
        with pytest.raises(ValueError):
            client.events(**kwargs)


@pytest.mark.parametrize(
    "timestamp,microsecond",
    [
        ("2026-09-30T12:00:00Z", 0),
        ("2026-09-30T12:00:00.1Z", 100000),
        ("2026-09-30T12:00:00.12Z", 120000),
        ("2026-09-30T12:00:00.123Z", 123000),
        ("2026-09-30T12:00:00.1234Z", 123400),
        ("2026-09-30T12:00:00.123456Z", 123456),
        ("2026-09-30T13:00:00.1+01:00", 100000),
    ],
)
def test_emsc_fractional_seconds(fixtures, timestamp, microsecond):
    data = copy.deepcopy(fixtures["emsc"])
    data["features"][0]["properties"]["time"] = timestamp
    event = parse_events(data, "emsc")[0]
    assert event.time == datetime(2026, 9, 30, 12, microsecond=microsecond, tzinfo=timezone.utc)
