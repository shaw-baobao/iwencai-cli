from __future__ import annotations

import argparse
import sys


def cmd_query(args: argparse.Namespace) -> None:
    from .query import query_iwencai, parse_results
    from .formatter import format_as_json, format_as_table
    from .installer import ensure_playwright

    if args.install_playwright:
        ensure_playwright(auto_install=True, auto_confirm=args.yes)

    if not args.question:
        print("请提供查询语句：-q '...'", file=sys.stderr)
        sys.exit(1)

    try:
        raw = query_iwencai(
            args.question,
            headless=not args.headful,
            profile_dir=args.profile_dir,
            wait_ms=args.wait_ms,
        )
        rows = parse_results(raw)
    except RuntimeError as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"查询失败：{e}", file=sys.stderr)
        sys.exit(1)

    if not rows:
        print("查询无结果")
        if args.raw:
            import json
            print(json.dumps(raw, ensure_ascii=False, indent=2))
        sys.exit(0)

    print(f"共 {len(rows)} 条结果：\n")
    if args.json:
        print(format_as_json(rows))
    else:
        print(format_as_table(rows))


def _add_query_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--question", "-q", type=str, required=True, help="自然语言查询语句")
    parser.add_argument("--headful", action="store_true", help="显示浏览器窗口（调试用）")
    parser.add_argument("--wait-ms", type=int, default=4000, help="页面加载后等待毫秒（默认 4000）")
    parser.add_argument("--profile-dir", type=str, default=None,
                        help="Playwright 持久化 profile 目录（默认 ~/.iwencai-profile）")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--raw", action="store_true", help="查询无结果时输出原始响应（调试用）")
    parser.add_argument("--install-playwright", action="store_true",
                        help="若未安装 Playwright，则自动安装")
    parser.add_argument("--yes", "-y", action="store_true", help="安装时跳过确认提示")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="iwencai-query",
        description="iWenCai 爱问财 — 自然语言选股查询 CLI",
    )
    _add_query_args(parser)
    args = parser.parse_args()
    cmd_query(args)
