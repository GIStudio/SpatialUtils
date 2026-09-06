"""本地 HTTP 桥: 供 SpatialHarness Web 工作台(AI 客户端)直接调用 Python 插件。

端点::

    GET  /health           → {"ok": true, "version": ...}
    GET  /plugins          → 全部已启用插件的 manifest(含输入/输出契约)
    POST /run/<plugin>     → body: {"data": <JSON>, "params": {...}} → 插件结果(JSON)

默认绑定 127.0.0.1（纯本地），响应带 CORS 头，便于 localhost:5173 开发服
与 gistudio.github.io 生产页直连。data 支持 list[记录] 与 GeoJSON
FeatureCollection（自动转 DataFrame，见 wire 层）。

运行::

    spatialharness serve              # 127.0.0.1:8765
    spatialharness serve --port 9000
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional, Tuple
from urllib.parse import urlparse

from . import __version__
from .core import PluginManager, SpatialUtilsError
from .wire import run_plugin_via_json


def make_handler(manager: PluginManager) -> type:
    class BridgeHandler(BaseHTTPRequestHandler):
        server_version = f"spatialharness/{__version__}"

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

        def do_OPTIONS(self) -> None:  # noqa: N802 - http.server 命名约定
            self._send(204, {})

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/")
            if path in ("", "/health"):
                self._send(200, {"ok": True, "version": __version__})
            elif path == "/plugins":
                self._send(200, {
                    name: info.as_dict()
                    for name, info in manager.list_plugins(only_enabled=True).items()
                })
            else:
                self._send(404, {"error": f"unknown path: {path}"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/")
            if not path.startswith("/run/"):
                self._send(404, {"error": f"unknown path: {path}"})
                return
            name = path[len("/run/"):]
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError) as exc:
                self._send(400, {"error": f"bad JSON body: {exc}"})
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
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def start_background(port: int = 0) -> Tuple[ThreadingHTTPServer, PluginManager]:
    """测试/嵌入用: 在随机端口启动并返回 server 实例。"""
    manager = PluginManager()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(manager))
    return httpd, manager
