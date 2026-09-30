"""Command-line interface (plain TSV when redirected)."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .cache import ResponseCache
from .client import QuakeClient
from .export import export_events
from .models import Event, QuakewatchError


def finite_float(value: str) -> float:
    try:
        result = float(value)
        if not math.isfinite(result):
            raise ValueError
        return result
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected a finite number") from exc


def coordinates(value: str) -> tuple[float, float]:
    try:
        lat, lon = (finite_float(part) for part in value.split(","))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError
        return lat, lon
    except (ValueError, argparse.ArgumentTypeError) as exc:
        raise argparse.ArgumentTypeError("Expected LAT,LON in [-90,90],[-180,180]") from exc


def render(headers: list[str], rows: list[list[str]]) -> None:
    if sys.stdout.isatty():
        table = Table(*headers)
        for row in rows:
            table.add_row(*row)
        Console(markup=False, highlight=False).print(table)
    else:
        for row in [headers, *rows]:
            print("\t".join(cell.replace("\t", " ").replace("\n", " ") for cell in row))


def show_events(events: list[Event]) -> None:
    render(
        ["ID", "Time (UTC)", "Mag", "Depth (km)", "Lat", "Lon", "Place", "Source"],
        [
            [
                event.id,
                str(event.as_dict()["time"]),
                "?" if event.magnitude is None else f"{event.magnitude:.2f}",
                "?" if event.depth_km is None else f"{event.depth_km:.2f}",
                f"{event.lat:.4f}",
                f"{event.lon:.4f}",
                event.place,
                event.source,
            ]
            for event in events
        ],
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="quakewatch", description="Recent USGS and EMSC earthquakes"
    )
    root.add_argument("--version", action="version", version="quakewatch 0.1.0")
    commands = root.add_subparsers(dest="command", required=True)
    for command in ("list", "export"):
        sub = commands.add_parser(command)
        sub.add_argument("--window", choices=("hour", "day", "week"), default="day")
        sub.add_argument("--source", choices=("usgs", "emsc", "both"), default="both")
        sub.add_argument("--min-mag", type=finite_float)
        sub.add_argument("--near", type=coordinates, metavar="LAT,LON")
        sub.add_argument("--radius-km", type=finite_float)
        sub.add_argument("--cache-ttl", type=finite_float, default=300, metavar="SECONDS")
        sub.add_argument("--cache-dir", type=Path, default=Path(".cache/quakewatch"))
        sub.add_argument("--no-cache", action="store_true")
        if command == "export":
            sub.add_argument("--format", choices=("csv", "json", "geojson"), required=True)
            sub.add_argument("--output", "-o", type=Path, required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        client = QuakeClient(ResponseCache(args.cache_dir, args.cache_ttl, not args.no_cache))
        events = client.events(
            window=args.window,
            source=args.source,
            min_mag=args.min_mag,
            near=args.near,
            radius_km=args.radius_km,
        )
        if args.command == "list":
            show_events(events)
        else:
            export_events(events, args.output, args.format)
            print(f"Exported {len(events)} events to {args.output}")
    except (QuakewatchError, OSError, ValueError) as exc:
        print(f"quakewatch: {exc}", file=sys.stderr)
        return 1
    return 0
