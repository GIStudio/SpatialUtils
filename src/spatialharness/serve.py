"""本地 HTTP 桥: 供 SpatialHarness Web 工作台(AI 客户端)直接调用 Python 插件。

插件计算端点::

    GET  /health           → {"ok": true, "version": ...}
    GET  /plugins          → 全部已启用插件的 manifest(含输入/输出契约)
    POST /run/<plugin>     → body: {"data": <JSON>, "params": {...}} → 插件结果(JSON)

AI 编辑中转队列（浏览器无法监听端口，由桥转发；见 docs/ai-editing.md）::

    POST /edit/submit      → body: {"tool", "args", "wait"?}；wait=true 长轮询结果
    GET  /edit/pending     → ?ack=<lastId> 浏览器轮询待执行命令（兼作心跳）
    POST /edit/result      → body: {"id", "ok", "summary"?|"error"?}
    GET  /edit/status      → {"browser_connected", "pending"}

默认绑定 127.0.0.1（纯本地），响应带 CORS 头。运行::

    spatialharness serve              # 127.0.0.1:8765
    spatialharness serve --port 9000
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from . import __version__
from .core import PluginManager, SpatialUtilsError
from .wire import run_plugin_via_json

BROWSER_TIMEOUT_S = 5.0  # 浏览器超过该秒数未轮询视为离线
EDIT_WAIT_S = 30.0  # submit wait 模式的最长等待


class EditQueue:
    """AI 编辑命令中转队列（线程安全）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._commands: List[Dict[str, Any]] = []
        self._results: Dict[int, Dict[str, Any]] = {}
        self._next_id = 1
        self._last_poll = 0.0

    def submit(self, tool: str, args: Dict[str, Any]) -> int:
        with self._lock:
            edit_id = self._next_id
            self._next_id += 1
            self._commands.append({"id": edit_id, "tool": tool, "args": args})
            return edit_id

    def pending_since(self, ack: int) -> Tuple[List[Dict[str, Any]], int]:
        """返回 ack 之后的所有命令与最新 id（并刷新心跳）。"""
        with self._lock:
            self._last_poll = time.time()
            commands = [c for c in self._commands if c["id"] > ack]
            return commands, (self._commands[-1]["id"] if self._commands else ack)

    def set_result(self, edit_id: int, payload: Dict[str, Any]) -> bool:
        with self._lock:
            known = any(c["id"] == edit_id for c in self._commands)
            if not known and edit_id not in self._results:
                return False  # 未知/重复结果，幂等丢弃
            self._results[edit_id] = payload
            return True

    def get_result(self, edit_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._results.get(edit_id)

    def wait_result(self, edit_id: int, timeout: float = EDIT_WAIT_S) -> Optional[Dict[str, Any]]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self.get_result(edit_id)
            if result is not None:
                return result
            time.sleep(0.15)
        return None

    def status(self) -> Dict[str, Any]:
        with self._lock:
            connected = (time.time() - self._last_poll) < BROWSER_TIMEOUT_S and self._last_poll > 0
            return {"browser_connected": connected, "pending": len(self._commands)}


def make_handler(manager: PluginManager, edit_queue: Optional[EditQueue] = None) -> type:
    queue = edit_queue or EditQueue()

    class BridgeHandler(BaseHTTPRequestHandler):
        server_version = f"spatialharness/{__version__}"
        edit_queue = queue

        def _send(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self) -> Optional[dict]:
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                return body if isinstance(body, dict) else None
            except (ValueError, json.JSONDecodeError):
                return None

        def do_OPTIONS(self) -> None:  # noqa: N802 - http.server 命名约定
            self._send(204, {})

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")
            if path in ("", "/health"):
                self._send(200, {"ok": True, "version": __version__})
            elif path == "/plugins":
                self._send(200, {
                    name: info.as_dict()
                    for name, info in manager.list_plugins(only_enabled=True).items()
                })
            elif path == "/edit/status":
                self._send(200, queue.status())
            elif path == "/edit/pending":
                qs = parse_qs(parsed.query)
                try:
                    ack = int(qs.get("ack", ["0"])[0])
                except ValueError:
                    self._send(400, {"error": "ack must be an integer"})
                    return
                commands, latest = queue.pending_since(ack)
                self._send(200, {"commands": commands, "latest": latest})
            else:
                self._send(404, {"error": f"unknown path: {path}"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/")
            if path == "/edit/submit":
                body = self._read_body()
                if body is None or not isinstance(body.get("tool"), str):
                    self._send(400, {"error": "body must be {tool, args, wait?}"})
                    return
                edit_id = queue.submit(body["tool"], body.get("args") or {})
                if body.get("wait"):
                    result = queue.wait_result(edit_id)
                    if result is None:
                        self._send(504, {"ok": False, "error": "timeout: Web 工作台未开启 AI 编辑或未响应"})
                    else:
                        self._send(200, result)
                else:
                    self._send(200, {"id": edit_id})
                return
            if path == "/edit/result":
                body = self._read_body()
                if body is None or not isinstance(body.get("id"), int):
                    self._send(400, {"error": "body must be {id, ok, summary?|error?}"})
                    return
                ok = queue.set_result(body["id"], {
                    "ok": bool(body.get("ok")),
                    "summary": body.get("summary") or body.get("error") or "",
                })
                self._send(200, {} if ok else {"error": "unknown edit id"})
                return
            if not path.startswith("/run/"):
                self._send(404, {"error": f"unknown path: {path}"})
                return
            name = path[len("/run/"):]
            body = self._read_body()
            if body is None:
                self._send(400, {"error": "bad JSON body"})
                return
            try:
                result = run_plugin_via_json(manager, name, body.get("data"), body.get("params"))
                self._send(200, {"ok": True, "result": result})
            except SpatialUtilsError as exc:
                self._send(400, {"ok": False, "error": str(exc)})
            except Exception as exc:  # noqa: BLE001 - 服务器不因单次调用崩溃
                self._send(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

        def log_message(self, fmt: str, *args: Any) -> None:  # 静默默认访问日志
            pass

    return BridgeHandler


def serve(host: str = "127.0.0.1", port: int = 8765, manager: Optional[PluginManager] = None) -> None:
    manager = manager or PluginManager()
    httpd = ThreadingHTTPServer((host, port), make_handler(manager))
    print(f"SpatialHarness Python 桥已启动: http://{host}:{port}  (Ctrl+C 退出)")
    print(f"  GET /health | GET /plugins | POST /run/<plugin>")
    print(f"  GET /edit/pending | POST /edit/submit | POST /edit/result | GET /edit/status")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def start_background(port: int = 0) -> Tuple[ThreadingHTTPServer, PluginManager, EditQueue]:
    """测试/嵌入用: 在随机端口启动并返回 server 实例与编辑队列。"""
    manager = PluginManager()
    queue = EditQueue()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(manager, queue))
    return httpd, manager, queue
