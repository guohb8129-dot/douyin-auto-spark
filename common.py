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
CONFIG_ALERT_FILE = DESKTOP / "抖音续火花-配置有误.txt"


def _toast(message: str) -> None:
    """弹一条 Windows 通知（WinRT Toast，零额外依赖）。"""
    # PowerShell 单引号字符串里，单引号自身需要写成两个。
    safe = message.replace("'", "''")
    ps = (
        "$ErrorActionPreference='SilentlyContinue';"
        "[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime];"
        "$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
        "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
        "$x=$t.GetElementsByTagName('text');"
        "$x.Item(0).AppendChild($t.CreateTextNode('抖音续火花')) > $null;"
        f"$x.Item(1).AppendChild($t.CreateTextNode('{safe}')) > $null;"
        "$n=[Windows.UI.Notifications.ToastNotification]::new($t);"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('DouyinSpark').Show($n)"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   timeout=20, capture_output=True)


def _alert(path: Path, toast_msg: str, body: str) -> None:
    """需人工介入的故障：写桌面告警文件，并尽力弹一条系统通知。"""
    try:
        path.write_text(body, encoding="utf-8")
    except Exception as exc:
        log(f"写告警文件失败：{exc}")
    try:
        _toast(toast_msg)
    except Exception as exc:
        log(f"弹窗通知失败（已写桌面文件）：{exc}")


def notify_login_lost() -> None:
    log("登录态已失效，需要重新扫码。")
    _alert(
        ALERT_FILE,
        "登录态已失效，续火花已暂停。请重新扫码。",
        f"时间：{_dt.datetime.now():%Y-%m-%d %H:%M}\n"
        f"抖音登录态已失效，自动续火花已暂停（登录成功后本文件会自动删除）。\n\n"
        f"请运行以下命令重新扫码：\n"
        f'  cd "{ROOT}"\n'
        f"  .venv\\Scripts\\python.exe login.py\n",
    )


def notify_config_error(detail: str) -> None:
    """配置无法解析时告警。它在发送流程之前发生，否则会静默失败。"""
    log(f"配置文件有误，本轮未发送：{detail}")
    _alert(
        CONFIG_ALERT_FILE,
        "config.json 有误，续火花已暂停。请检查标点。",
        f"时间：{_dt.datetime.now():%Y-%m-%d %H:%M}\n"
        f"config.json 解析失败，自动续火花已暂停（改好后本文件会自动删除）。\n\n"
        f"错误：{detail}\n\n"
        f"最常见的原因：编辑时用了中文输入法，打出了全角标点，\n"
        f"例如全角逗号 ， 、中文引号 “ ” 、全角冒号 ： 。\n"
        f"JSON 只接受半角标点： , \" :\n\n"
        f"请检查该文件：\n  {CONFIG_PATH}\n\n"
        f"改完自检：\n"
        f'  cd "{ROOT}"\n'
        f"  .venv\\Scripts\\python.exe -c \"import json;print(json.load(open('config.json',encoding='utf-8'))['targets'])\"\n",
    )


def clear_login_alert() -> None:
    try:
        ALERT_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def clear_config_alert() -> None:
    try:
        CONFIG_ALERT_FILE.unlink(missing_ok=True)
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
