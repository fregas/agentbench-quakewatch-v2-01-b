from dataclasses import replace
from datetime import timedelta
from itertools import permutations

import pytest

from quakewatch import compare_events
from quakewatch.cli import main, show_comparison


def test_match_and_magnitude(event):
    other = replace(
        event,
        id="e1",
        source="emsc",
        time=event.time + timedelta(seconds=60),
        lon=0.1,
        magnitude=4.2,
    )
    result = compare_events([event, other])
    assert len(result.matches) == 1
    match = result.matches[0]
    assert match.time_difference_s == 60
    assert match.distance_km == pytest.approx(11.1195, abs=0.001)
    assert match.magnitude_difference == pytest.approx(0.3)
    assert not result.unmatched_usgs and not result.unmatched_emsc
    for dt in [-60, 60]:
        assert (
            len(
                compare_events(
                    [event, replace(other, time=event.time + timedelta(seconds=dt))]
                ).matches
            )
            == 1
        )
    for dt in [-60.001, 60.001]:
        assert not compare_events(
            [event, replace(other, time=event.time + timedelta(seconds=dt))]
        ).matches
    assert not compare_events([event, replace(other, lon=1)]).matches


def test_inclusive_distance(event, monkeypatch):
    other = replace(event, source="emsc")
    monkeypatch.setattr("quakewatch.compare.distance_km", lambda *a: 50)
    assert len(compare_events([event, other]).matches) == 1
    monkeypatch.setattr("quakewatch.compare.distance_km", lambda *a: 50.00001)
    assert not compare_events([event, other]).matches


def test_augmenting_path_avoids_greedy_loss(event):
    # u1 can use e1/e2, u2 only e1. Initial nearest match u1->e1 must be moved.
    u1 = event
    u2 = replace(event, id="u2", time=event.time + timedelta(seconds=70))
    e1 = replace(event, id="e1", source="emsc", time=event.time + timedelta(seconds=20))
    e2 = replace(event, id="e2", source="emsc", time=event.time - timedelta(seconds=50))
    for order in permutations([u1, u2, e1, e2]):
        result = compare_events(list(order))
        assert [(m.usgs.id, m.emsc.id) for m in result.matches] == [("u1", "e2"), ("u2", "e1")]


def test_one_to_one_and_empty(event):
    events = [
        event,
        replace(event, id="u2"),
        replace(event, id="u3"),
        replace(event, id="e1", source="emsc"),
    ]
    result = compare_events(events)
    assert len(result.matches) == 1
    assert len(result.unmatched_usgs) == 2
    assert not result.unmatched_emsc
    assert not compare_events([]).matches
    assert compare_events([event]).unmatched_usgs == (event,)
    other = replace(event, source="emsc")
    assert compare_events([other]).unmatched_emsc == (other,)


def test_unknown_and_cli(event, monkeypatch, capsys):
    for source in ("usgs", "emsc"):
        events = [event, replace(event, id="e1", source="emsc")]
        events = [replace(e, magnitude=None) if e.source == source else e for e in events]
        result = compare_events(events)
        assert result.matches[0].magnitude_difference is None
        show_comparison(result)
        assert "?" in capsys.readouterr().out
    monkeypatch.setattr(
        "quakewatch.cli.QuakeClient.events",
        lambda self, **kw: [event, replace(event, id="e1", source="emsc", magnitude=4)],
    )
    assert main(["compare", "--window", "day", "--no-cache"]) == 0
    output = capsys.readouterr().out
    assert (
        "Matched: 1" in output and "Unmatched USGS: 0" in output and "Unmatched EMSC: 0" in output
    )
    assert "+0.50" in output and "\x1b" not in output
