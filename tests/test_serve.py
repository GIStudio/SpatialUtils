from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from spatialharness.serve import start_background


@pytest.fixture(scope="module")
def server():
    httpd, _mgr = start_background(port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def _base(server) -> str:
    host, port = server.server_address[:2]
    return f"http://{host}:{port}"


def _get(server, path: str):
    with urllib.request.urlopen(_base(server) + path, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8")), resp.headers


def _post(server, path: str, body: dict):
    req = urllib.request.Request(
        _base(server) + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def test_health(server):
    status, body, headers = _get(server, "/health")
    assert status == 200
    assert body["ok"] is True
    assert headers["Access-Control-Allow-Origin"] == "*"


def test_plugins_listing(server):
    status, body, _ = _get(server, "/plugins")
    assert status == 200
    assert "spatial_accessibility" in body
    assert body["street_solar"]["input_contract"] == {"folder": "path"}


def test_run_hello(server):
    status, body = _post(server, "/run/hello", {"params": {"who": "HTTP"}})
    assert status == 200
    assert body["ok"] is True
    assert "HTTP" in body["result"]["message"]


def test_run_unknown_plugin_is_400(server):
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post(server, "/run/nope", {})
    assert excinfo.value.code == 400
    assert "nope" in excinfo.value.read().decode("utf-8")


def test_unknown_path_is_404(server):
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _get(server, "/whatever")
    assert excinfo.value.code == 404
