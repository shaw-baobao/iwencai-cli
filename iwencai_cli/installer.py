from __future__ import annotations

import subprocess
import sys


def is_playwright_installed() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def install_playwright(auto_confirm: bool = False) -> bool:
    """Install the playwright Python package.

    Chromium download is skipped — we use the user's real Chrome (channel="chrome").
    """
    if is_playwright_installed():
        return True

    if not auto_confirm:
        print("检测到缺少 Playwright（用于自动打开浏览器抓取数据）", file=sys.stderr)
        reply = input("是否现在安装？[y/N] ").strip().lower()
        if reply not in ("y", "yes"):
            print("已取消安装", file=sys.stderr)
            return False

    print("正在安装 playwright...", file=sys.stderr)
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "playwright>=1.30"]
        )
    except subprocess.CalledProcessError as e:
        print(f"安装 playwright 失败: {e}", file=sys.stderr)
        return False

    print("Playwright 安装完成（使用本机 Chrome，无需下载 Chromium）", file=sys.stderr)
    return True


def ensure_playwright(auto_install: bool = False, auto_confirm: bool = False) -> bool:
    if is_playwright_installed():
        return True
    if not auto_install:
        return False
    return install_playwright(auto_confirm=auto_confirm)
