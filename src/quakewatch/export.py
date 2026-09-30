"""Portable exports with UTC timestamps and explicit depth units."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Literal

from .models import Event

ExportFormat = Literal["csv", "json", "geojson"]
FIELDS = ["id", "time", "magnitude", "depth_km", "lat", "lon", "place", "source"]


def export_events(events: list[Event], path: Path, format: ExportFormat) -> None:
    if format not in ("csv", "json", "geojson"):
        raise ValueError("Unsupported export format")
    rows = [event.as_dict() for event in events]
    with path.open("w", encoding="utf-8", newline="") as handle:
        if format == "csv":
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        elif format == "json":
            json.dump(rows, handle, indent=2, allow_nan=False)
            handle.write("\n")
        else:
            json.dump(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "id": f"{event.source}:{event.id}",
                            "geometry": {"type": "Point", "coordinates": [event.lon, event.lat]},
                            "properties": row,
                        }
                        for event, row in zip(events, rows, strict=True)
                    ],
                },
                handle,
                indent=2,
                allow_nan=False,
            )
            handle.write("\n")
