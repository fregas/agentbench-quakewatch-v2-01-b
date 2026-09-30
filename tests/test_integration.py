from datetime import datetime, timedelta, timezone

import pytest

from quakewatch import QuakeClient, ResponseCache


@pytest.mark.integration
@pytest.mark.parametrize("source", ["usgs", "emsc"])
def test_live_api(source):
    now = datetime.now(timezone.utc)
    events = QuakeClient(ResponseCache(enabled=False)).events(source=source, window="day", now=now)
    assert events, f"{source} unexpectedly returned no earthquakes in a full day"
    assert all(e.source == source for e in events)
    assert all(now - timedelta(days=1) <= e.time <= now for e in events)
    assert all(-90 <= e.lat <= 90 and -180 <= e.lon <= 180 for e in events)
