import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from quakewatch import Event


@pytest.fixture
def fixtures():
    return {
        name: json.loads((Path(__file__).parent / "fixtures" / f"{name}.json").read_text())
        for name in ("usgs", "emsc")
    }


@pytest.fixture
def event():
    return Event(
        "u1", datetime(2026, 9, 30, 12, tzinfo=timezone.utc), 4.5, 10, 0, 0, "Test", "usgs"
    )
