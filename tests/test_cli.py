from __future__ import annotations

import json

from spatialharness.cli import main


def test_cli_list(capsys):
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "spatial_accessibility" in out
    assert "street_solar" in out


def test_cli_list_json(capsys):
    assert main(["list", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["street_solar"]["category"] == "streetview"


def test_cli_show(capsys):
    assert main(["show", "street_solar"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["input_contract"] == {"folder": "path"}


def test_cli_run_hello(capsys):
    assert main(["run", "hello", "--param", "who=GIS"]) == 0
    out = capsys.readouterr().out
    assert "message" in out
