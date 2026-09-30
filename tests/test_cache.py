import json
from unittest.mock import Mock

import pytest

from quakewatch import ResponseCache


def test_hit_expire_corrupt(tmp_path, monkeypatch):
    monkeypatch.setattr("quakewatch.cache.time.time", lambda: 100)
    loader = Mock(return_value={"type": "FeatureCollection", "features": []})
    cache = ResponseCache(tmp_path, ttl=10)
    assert cache.get("a", loader) == loader.return_value
    assert cache.get("a", loader) == loader.return_value
    assert loader.call_count == 1
    monkeypatch.setattr("quakewatch.cache.time.time", lambda: 110)
    cache.get("a", loader)
    assert loader.call_count == 2
    path = next(tmp_path.glob("*.json"))
    for bad in (
        "broken",
        "[]",
        "{}",
        '{"saved_at": "bad"}',
        json.dumps({"saved_at": 110, "response": []}),
        json.dumps({"saved_at": 200, "response": {}}),
    ):
        path.write_text(bad)
        cache.get("a", loader)
    assert loader.call_count == 8
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize("kwargs", [{"enabled": False}, {"ttl": 0}])
def test_bypass(tmp_path, kwargs):
    loader = Mock(return_value={})
    directory = tmp_path / "absent"
    cache = ResponseCache(directory, **kwargs)
    cache.get("a", loader)
    cache.get("a", loader)
    assert loader.call_count == 2
    assert not directory.exists()


def test_cache_invalid_and_failed_fetch(tmp_path):
    for ttl in (-1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            ResponseCache(tmp_path, ttl=ttl)
    with pytest.raises(RuntimeError):
        ResponseCache(tmp_path).get("a", Mock(side_effect=RuntimeError("offline")))
    assert not list(tmp_path.iterdir())
