"""Command line interface.

Examples::

    spatialharness list
    spatialharness list --all
    spatialharness show street_solar
    spatialharness run street_solar --param folder=./tests/data/photos
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .core import PluginManager


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spatialharness",
        description="插件式 GIS / 城市科学工具库 (core = 插件管理 + 数据契约)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="列出已注册插件")
    p_list.add_argument("--all", action="store_true", help="包含已禁用的插件")
    p_list.add_argument("--json", action="store_true", dest="as_json", help="JSON 输出")

    p_show = sub.add_parser("show", help="查看插件详情与数据契约")
    p_show.add_argument("name")

    p_run = sub.add_parser("run", help="运行插件")
    p_run.add_argument("name")
    p_run.add_argument("--param", action="append", default=[], metavar="K=V",
                       help="插件参数，可重复；布尔值用 true/false")

    p_enable = sub.add_parser("enable", help="启用插件")
    p_enable.add_argument("name")
    p_disable = sub.add_parser("disable", help="禁用插件（仅本次进程内生效）")
    p_disable.add_argument("name")

    return parser


def _coerce(value: str) -> object:
    low = value.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    mgr = PluginManager()

    if args.command == "list":
        plugins = mgr.list_plugins()
        if getattr(args, "as_json", False):
            print(json.dumps({n: i.as_dict() for n, i in plugins.items()},
                             ensure_ascii=False, indent=2))
            return 0
        if not plugins:
            print("（没有已启用的插件）")
            return 0
        width = max(len(n) for n in plugins) + 2
        for name, info in plugins.items():
            status = "" if mgr.is_enabled(name) else "  [disabled]"
            print(f"{name:<{width}}{info.version:<10}{info.category:<16}{info.description}{status}")
        return 0

    if args.command == "show":
        info = mgr.get(args.name).info()
        print(json.dumps(info.as_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "run":
        params = {}
        for kv in args.param:
            if "=" not in kv:
                print(f"参数格式应为 K=V: {kv!r}", file=sys.stderr)
                return 2
            key, value = kv.split("=", 1)
            params[key.strip()] = _coerce(value)
        result = mgr.run(args.name, **params)
        from .core.contracts import describe_payload

        print(describe_payload(result))
        return 0

    if args.command == "enable":
        mgr.enable(args.name)
        print(f"enabled: {args.name}")
        return 0

    if args.command == "disable":
        mgr.disable(args.name)
        print(f"disabled: {args.name}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
