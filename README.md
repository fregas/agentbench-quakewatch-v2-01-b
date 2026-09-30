# quakewatch

A Python 3.10+ CLI and typed library for recent earthquakes from USGS and EMSC.

## Install

From this checkout:

```sh
python3 -m venv .venv
PIP_CACHE_DIR=./.cache/pip .venv/bin/pip install .
.venv/bin/quakewatch --help
```

Or install a downloaded release wheel with `.venv/bin/pip install ./quakewatch-0.1.0-py3-none-any.whl`.

## Usage

```sh
quakewatch list --window day
quakewatch list --window week --min-mag 4 --source both
quakewatch list --window hour --source usgs --near 37.77,-122.42 --radius-km 200
quakewatch compare --window day
quakewatch compare --window week --min-mag 4 --no-cache
quakewatch export --window day --format csv --output earthquakes.csv
quakewatch export --window week --min-mag 3 --format json -o earthquakes.json
quakewatch export --window day --format geojson -o earthquakes.geojson
```

Defaults: both sources, past day, no magnitude threshold. Windows are rolling UTC
hour/day/seven-day intervals. `--near` and `--radius-km` must be supplied together;
radius uses great-circle surface distance. Unknown magnitudes are retained unless
`--min-mag` is specified. Unknown magnitude/depth is shown as `?` in tables and
`null` in JSON (empty in CSV). Negative depths are preserved.

Terminals get Rich tables; pipes/files get plain tab-separated output. Errors go
to stderr with a nonzero exit status. A source failure fails the command rather
than silently returning a partial catalogue. Exports overwrite the specified file.
GeoJSON uses `[longitude, latitude]` points with depth in the `depth_km` property;
this avoids confusing depth in kilometers with GeoJSON altitude in meters.

## Comparing catalogues

`compare` always fetches both sources. Reports within **60 seconds (inclusive)**
and **50 km (inclusive)** are candidate matches. Matching is one-to-one and
maximizes the number of pairs; candidates prefer smaller time difference, then
distance and ID for deterministic ties. Ambiguous dense sequences may have more
than one valid assignment. This heuristic does not prove event identity or
minimize the total time/distance across all pairs.

Output includes matched-pair count, unmatched counts per source, each matched
pair's time/distance separation, and signed magnitude difference **USGS − EMSC**.
Unknown differences are `?`. Filters apply to each catalogue before matching;
a magnitude threshold can therefore leave a pair unmatched when one source
reports a lower magnitude. No matches yields zero counts plus column headings.

## Cache

Responses are cached in `./.cache/quakewatch` for 300 seconds. Use
`--cache-ttl 60`, `--cache-dir PATH`, or `--no-cache` after the subcommand.
TTL zero also bypasses both cache reads and writes. Keys identify source/window,
so successive EMSC calls reuse a response even as the clock advances. Cached
results are filtered against the current time window; newly reported events may
remain absent until TTL expiry. Corrupt entries are refetched and writes are atomic.

## Library

```python
from pathlib import Path
from quakewatch import QuakeClient, ResponseCache, compare_events, export_events

client = QuakeClient(ResponseCache(ttl=60))
events = client.events(window="day", source="both", min_mag=4)
comparison = compare_events(events)
print(len(comparison.matches))
export_events(events, Path("earthquakes.geojson"), "geojson")
```

`Event` contains `id`, timezone-aware UTC `time`, `magnitude`, `depth_km`, `lat`,
`lon`, `place`, and `source`. IDs are source-specific. Listing both catalogues
preserves both reports; it does not deduplicate them. HTTP requests have a
30-second timeout and retry connection failures twice. EMSC queries paginate
at 20,000 events. An optional `httpx.Client` can be injected into `QuakeClient`.

## Known source differences

[USGS summary feeds](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php)
encode time as Unix milliseconds and depth in the third coordinate.
[EMSC's FDSN service](https://www.seismicportal.eu/fdsn-wsevent.html) with
`format=json` supplies ISO times, region names, and a `properties.depth` value in
kilometers; its vertical coordinate uses the opposite sign. Quakewatch uses
EMSC's depth property and converts both time formats to UTC.

Catalogue coverage, publication delays, location estimates, and magnitude types
can differ. Magnitudes are reported values, not converted to a common scale.
Recent entries can be revised. EMSC data is attributed to EMSC / SeismicPortal
and distributed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Recorded test fixtures are small unmodified feature samples from these services;
see `tests/fixtures/README.md` for recording details.

## Development

```sh
PIP_CACHE_DIR=./.cache/pip .venv/bin/pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy --strict src
.venv/bin/pytest -m 'not integration' --cov=quakewatch --cov-report=xml --cov-report=term-missing
.venv/bin/pytest -m integration -v
```

The unit suite mocks HTTP and enforces at least 85% branch-aware coverage.
Integration tests call each real API without a cache. CI runs lint, typing and
unit tests on Python 3.10/3.11/3.12 and live integration tests separately on 3.12.
Coverage XML artifacts are uploaded for every matrix member.

```sh
docker build -t agentbench-quakewatch-v2-01-b:local .
docker run --rm --name agentbench-quakewatch-list agentbench-quakewatch-v2-01-b:local list --window day
```

The multi-stage image uses Python slim and runs as UID/GID 10001 with a writable
`/app` working directory for its cache. Tags matching `v*` build an sdist, wheel,
and Docker image, then attach both Python distributions to a GitHub Release.
The image is built and smoke-tested by the release job; it is not pushed to a registry.
