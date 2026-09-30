import csv
import json
import subprocess
import sys
from dataclasses import replace

import pytest

from quakewatch import QuakewatchError, export_events
from quakewatch.cli import main, show_events


@pytest.mark.parametrize("format", ["csv", "json", "geojson"])
def test_export(format, tmp_path, event):
    path = tmp_path / ("events." + format)
    events = [event, replace(event, id="missing", magnitude=None, depth_km=None, place="A, B\nC")]
    export_events(events, path, format)
    if format == "csv":
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert rows[0]["time"].endswith("Z")
        assert rows[1]["magnitude"] == ""
        assert rows[1]["place"] == "A, B\nC"
    else:
        data = json.loads(path.read_text())
        if format == "geojson":
            assert data["type"] == "FeatureCollection"
            assert data["features"][0]["geometry"]["coordinates"] == [0, 0]
            assert data["features"][0]["id"] == "usgs:u1"
            data = [feature["properties"] for feature in data["features"]]
        assert data[0]["depth_km"] == 10
        assert data[1]["magnitude"] is None
    export_events([], path, format)
    assert path.stat().st_size > 0
    with pytest.raises(ValueError):
        export_events([], path, "xml")


def test_cli_list_export(monkeypatch, capsys, event, tmp_path):
    monkeypatch.setattr("quakewatch.cli.QuakeClient.events", lambda self, **kw: [event])
    assert (
        main(["list", "--window", "hour", "--near", "0,0", "--radius-km", "20", "--no-cache"]) == 0
    )
    output = capsys.readouterr().out
    assert "Time (UTC)\tMag" in output and "\x1b" not in output and "u1" in output
    path = tmp_path / "out.json"
    assert main(["export", "--format", "json", "-o", str(path)]) == 0
    assert json.loads(path.read_text())[0]["id"] == "u1"
    assert "Exported 1" in capsys.readouterr().out


def test_unknown_and_terminal(monkeypatch, capsys, event):
    show_events([replace(event, magnitude=None, depth_km=None, place="Test\tline\nbreak")])
    assert "?\t?" in capsys.readouterr().out
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    show_events([event])
    assert "━" in capsys.readouterr().out


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["list", "--near", "oops"],
        ["list", "--near", "91,0"],
        ["list", "--near", "nan,0"],
        ["list", "--near", "0,0,0"],
        ["list", "--min-mag", "nan"],
        ["list", "--min-mag", "bad"],
        ["list", "--window", "year"],
        ["export", "--format", "json"],
    ],
)
def test_parser_errors(arguments):
    with pytest.raises(SystemExit) as exc:
        main(arguments)
    assert exc.value.code == 2


def test_error_output(monkeypatch, capsys):
    def fail(self, **kwargs):
        raise QuakewatchError("offline")

    monkeypatch.setattr("quakewatch.cli.QuakeClient.events", fail)
    assert main(["list"]) == 1
    assert "offline" in capsys.readouterr().err
    assert main(["list", "--cache-ttl", "-1"]) == 1


def test_module_entrypoint():
    result = subprocess.run(
        [sys.executable, "-m", "quakewatch", "--version"], text=True, capture_output=True
    )
    assert result.returncode == 0
    assert "0.1.0" in result.stdout
