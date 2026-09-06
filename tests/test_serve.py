from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from spatialharness.serve import start_background


@pytest.fixture(scope="module")
def server():
    httpd, _mgr, _queue = start_background(port=0)
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


# ---------------- AI 编辑中转队列 ----------------

def test_edit_roundtrip(server):
    """submit(不等待) → pending 取命令 → result 回传 → wait 模式取到结果。"""
    status, body = _post(server, "/edit/submit", {"tool": "map_status", "args": {}})
    assert status == 200 and isinstance(body["id"], int)
    edit_id = body["id"]

    # 浏览器视角: 取命令
    status, body, _ = _get(server, "/edit/pending?ack=0")
    assert status == 200
    assert any(c["id"] == edit_id and c["tool"] == "map_status" for c in body["commands"])

    # 回传结果
    status, body = _post(server, "/edit/result", {"id": edit_id, "ok": True, "summary": "ok"})
    assert status == 200

    # wait 模式端到端: 后台 submit(wait), 主线程扮演浏览器取命令并回传结果
    import threading
    holder = {}

    def waiter():
        _status, _body = _post(server, "/edit/submit", {"tool": "map_status", "args": {}, "wait": True})
        holder["status"], holder["body"] = _status, _body

    t = threading.Thread(target=waiter)
    t.start()
    status, body, _ = _get(server, f"/edit/pending?ack={edit_id}")
    new_cmds = [c for c in body["commands"] if c["id"] > edit_id]
    assert new_cmds, "wait 模式的新命令应出现在 pending 中"
    _post(server, "/edit/result", {"id": new_cmds[-1]["id"], "ok": True, "summary": "wait-ok"})
    t.join(10)
    assert not t.is_alive()
    assert holder["body"]["ok"] is True and holder["body"]["summary"] == "wait-ok"


def test_edit_pending_ack_increments(server):
    status, body = _post(server, "/edit/submit", {"tool": "map_status", "args": {}})
    new_id = body["id"]
    status, body, _ = _get(server, f"/edit/pending?ack={new_id}")
    assert status == 200
    assert body["commands"] == []  # ack 游标之后无新命令


def test_edit_unknown_result_id_rejected(server):
    status, body = _post(server, "/edit/result", {"id": 999999, "ok": True})
    assert status == 200  # 幂等丢弃: 200 + error 字段
    assert body.get("error") == "unknown edit id"


def test_edit_status_heartbeat(server):
    # 刚轮询过 pending，浏览器应视为在线
    _get(server, "/edit/pending?ack=999999")
    status, body, _ = _get(server, "/edit/status")
    assert status == 200
    assert body["browser_connected"] is True


def test_edit_submit_bad_body_400(server):
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post(server, "/edit/submit", {"args": {}})
    assert excinfo.value.code == 400
