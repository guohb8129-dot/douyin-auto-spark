"""抖音续火花自动化 —— 公共模块：浏览器启动、登录态判定、日志。

用真实 Chrome + 持久化用户目录启动，既保留登录态，又避免 headless 被抖音
下发占位二维码 / 触发人机验证。
"""
from __future__ import annotations

import datetime as _dt
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import BrowserContext, Page

# 中文日志在部分 Windows 控制台会因默认编码报错，这里统一为 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
PROFILE_DIR = ROOT / "profile"          # 持久化浏览器配置，登录态就存在这里
CONFIG_PATH = ROOT / "config.json"
LOG_DIR = ROOT / "logs"
CHAT_URL = "https://www.douyin.com/chat"

CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    str(Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)

# 登录后必然出现的会话级 Cookie，任一存在即视为已登录。
SESSION_COOKIES = {"sessionid", "sessionid_ss", "sid_tt"}


def find_chrome() -> str:
    for path in CHROME_CANDIDATES:
        if Path(path).is_file():
            return path
    raise SystemExit("未找到 Chrome/Edge，请先安装 Chrome 再重试。")


def log(msg: str) -> None:
    line = f"[{_dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(exist_ok=True)
    with (LOG_DIR / f"{_dt.date.today():%Y%m}.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


DESKTOP = Path.home() / "Desktop"
ALERT_FILE = DESKTOP / "抖音续火花-需要重新登录.txt"

# 隐藏窗口运行的一次性通知脚本（WinRT Toast，零额外依赖）。
_TOAST_PS = (
    "$ErrorActionPreference='SilentlyContinue';"
    "[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime];"
    "$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
    "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
    "$x=$t.GetElementsByTagName('text');"
    "$x.Item(0).AppendChild($t.CreateTextNode('抖音续火花')) > $null;"
    "$x.Item(1).AppendChild($t.CreateTextNode('登录态已失效，续火花已暂停。请重新扫码。')) > $null;"
    "$n=[Windows.UI.Notifications.ToastNotification]::new($t);"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('DouyinSpark').Show($n)"
)


def notify_login_lost() -> None:
    """登录态失效需人工介入：写桌面告警文件，并尽力弹一条 Windows 通知。"""
    log("登录态已失效，需要重新扫码。")
    try:
        ALERT_FILE.write_text(
            f"时间：{_dt.datetime.now():%Y-%m-%d %H:%M}\n"
            f"抖音登录态已失效，自动续火花已暂停（登录成功后本文件会自动删除）。\n\n"
            f"请运行以下命令重新扫码：\n"
            f'  cd "{ROOT}"\n'
            f"  .venv\\Scripts\\python.exe login.py\n",
            encoding="utf-8",
        )
    except Exception as exc:
        log(f"写桌面告警文件失败：{exc}")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", _TOAST_PS],
                       timeout=20, capture_output=True)
    except Exception as exc:
        log(f"弹窗通知失败（已写桌面文件）：{exc}")


def clear_login_alert() -> None:
    try:
        ALERT_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def launch(pw, headless: bool) -> BrowserContext:
    PROFILE_DIR.mkdir(exist_ok=True)
    return pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        executable_path=find_chrome(),
        headless=headless,
        viewport={"width": 1280, "height": 800},
        locale="zh-CN",
        args=["--disable-blink-features=AutomationControlled"],
    )


def is_logged_in(page: Page) -> bool:
    try:
        names = {c.get("name") for c in page.context.cookies()}
        if names & SESSION_COOKIES:
            return True
        return bool(page.evaluate("() => localStorage.getItem('HasUserLogin') === '1'"))
    except Exception:
        return False
