"""抖音续火花 —— 每天定时给指定好友发一条私信。

用法：
    python spark.py              正常发送
    python spark.py --dry-run    只演练：定位会话、填入文字，不点发送
    python spark.py --now        立即发送一轮（不等定时）
    python spark.py --list       打印当前会话列表，用于确认好友昵称
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import random
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from common import (
    CHAT_URL,
    CONFIG_PATH,
    LOG_DIR,
    clear_config_alert,
    is_logged_in,
    launch,
    log,
    notify_config_error,
    notify_login_lost,
)

# 以下选择器均在 2026-10 的抖音网页版上实测确认。
# 输入框：Draft.js 富文本（data-placeholder="发送消息"）。
INPUT_SELECTORS = (
    '[contenteditable="true"]',
    'div[class*="messageEditor"] [contenteditable="true"]',
    'textarea',
)
# 发送按钮：圆形上箭头，带 e2e 测试钩子，比哈希类名稳定。
SEND_SELECTORS = (
    '.e2e-send-msg-btn',
    '[class*="publishBtn"]',
    'svg[class*="publishBtn"]',
)
# 会话标题：仅包含对方昵称，用于确认切换对了人。
HEADER_SELECTORS = (
    '.RightPanelHeadertitle',
    '[class*="RightPanelHeadertitle"]',
    '[class*="convHeader"]',
)
# 会话列表项：抖音类名是动态哈希，用语义化属性兜底。
LIST_SELECTORS = (
    '[class*="conversation"] [class*="item"]',
    '[role="listitem"]',
    '[class*="conversationItem"]',
    '[class*="sessionItem"]',
)
# 风控提示只会出现在弹窗/浮层里。绝不能扫全页文本——会话预览里也可能出现同类词。
RATE_LIMIT_MARKERS = ("操作频繁", "安全验证", "请完成验证", "发送过于频繁", "稍后再试")
RATE_LIMIT_SELECTORS = (
    '[class*="toast"]',
    '[role="alert"]',
    '[class*="dialog"]',
    '[class*="modal"]',
    '[class*="notification"]',
)


# 非半角标点：出现在 JSON 结构位置就会让文件解析失败。
BAD_PUNCT = {
    "\uff0c": "全角逗号", "\uff1a": "全角冒号", "\uff1b": "全角分号",
    "\u201c": "中文左引号", "\u201d": "中文右引号",
    "\uff08": "全角左括号", "\uff09": "全角右括号",
    "\u3010": "全角左方括号", "\u3011": "全角右方括号",
    "\uff1d": "全角等号", "\u3002": "中文句号",
}


class ConfigError(Exception):
    """配置无法加载，附带可操作的修复说明。"""


def _diagnose_json_error(raw: str, exc: Exception) -> str:
    """把 JSONDecodeError 转成带行号与可疑标点的说明。"""
    msg = str(exc)
    for ch, name in BAD_PUNCT.items():
        if ch in raw:
            line = next((i for i, ln in enumerate(raw.splitlines(), 1) if ch in ln), 0)
            return f"{msg}\n第 {line} 行出现{name}「{ch}」，JSON 只接受半角标点。"
    return msg


def load_config() -> dict:
    if not CONFIG_PATH.is_file():
        raise ConfigError(f"缺少配置文件：{CONFIG_PATH}")
    raw = CONFIG_PATH.read_text(encoding="utf-8")
    try:
        cfg = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(_diagnose_json_error(raw, exc)) from exc
    if not cfg.get("targets"):
        raise ConfigError("config.json 里的 targets 为空，请填写好友昵称。")
    if not cfg.get("messages"):
        raise ConfigError("config.json 里的 messages 为空，请填写至少一条消息。")
    return cfg


def load_config_or_alert() -> dict | None:
    """配置有问题时告警并返回 None，避免静默失败。"""
    try:
        cfg = load_config()
    except ConfigError as exc:
        notify_config_error(str(exc))
        return None
    clear_config_alert()
    return cfg


def first_visible(page: Page, selectors):
    for sel in selectors:
        loc = page.locator(sel)
        try:
            count = min(loc.count(), 5)
        except Exception:
            continue
        for i in range(count):
            item = loc.nth(i)
            try:
                if item.is_visible():
                    return item
            except Exception:
                continue
    return None


def rate_limited(page: Page) -> bool:
    """只在可见的弹窗/提示浮层里匹配风控文案。"""
    for sel in RATE_LIMIT_SELECTORS:
        loc = page.locator(sel)
        try:
            n = min(loc.count(), 5)
        except Exception:
            continue
        for i in range(n):
            try:
                el = loc.nth(i)
                if el.is_visible() and any(m in (el.inner_text() or "") for m in RATE_LIMIT_MARKERS):
                    return True
            except Exception:
                continue
    return False


def dump_debug(page: Page, tag: str) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        page.screenshot(path=str(LOG_DIR / f"{tag}-{ts}.png"), full_page=True)
        (LOG_DIR / f"{tag}-{ts}.html").write_text(page.content(), encoding="utf-8")
        log(f"已保存现场：logs/{tag}-{ts}.png / .html")
    except Exception as exc:
        log(f"保存现场失败：{exc}")


def open_chat(page: Page, target: str) -> bool:
    """打开聊天页并切到目标会话，校验右侧标题确实是目标昵称。"""
    page.goto(CHAT_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(8000)          # 等会话列表异步渲染
    if not is_logged_in(page):
        notify_login_lost()
        return False

    # 1) 先在最近会话列表里点
    loc = page.get_by_text(target, exact=True)
    if loc.count() > 0:
        try:
            loc.first.click(timeout=5000)
            page.wait_for_timeout(1500)
            if _header_matches(page, target):
                return True
            log(f"点击“{target}”后标题不匹配，改用搜索兜底。")
        except Exception as exc:
            log(f"列表点击失败：{exc}")

    # 2) 搜索兜底
    box = page.locator('input[placeholder*="搜索"]').first
    if box.count() > 0:
        try:
            box.click(timeout=5000)
            box.fill(target)
            page.wait_for_timeout(2500)
            hit = page.get_by_text(target, exact=True)
            if hit.count() > 0:
                hit.first.click(timeout=5000)
                page.wait_for_timeout(2000)
                if _header_matches(page, target):
                    return True
        except Exception as exc:
            log(f"搜索兜底失败：{exc}")

    log(f"找不到会话“{target}”（或无法确认切换成功）。")
    dump_debug(page, "cant-open-chat")
    return False


def _header_matches(page: Page, target: str) -> bool:
    """确认已切到目标会话，避免把消息发给上一个联系人。"""
    for sel in HEADER_SELECTORS:
        loc = page.locator(sel)
        try:
            count = min(loc.count(), 8)
        except Exception:
            continue
        for i in range(count):
            try:
                if loc.nth(i).is_visible() and target in (loc.nth(i).inner_text() or ""):
                    return True
            except Exception:
                continue
    return False


def type_message(page: Page, message: str) -> bool:
    """向 Draft.js 输入框写入文字。insert_text 失败时退回剪贴板粘贴。"""
    box = first_visible(page, INPUT_SELECTORS)
    if box is None:
        log("找不到输入框。")
        return False
    try:
        box.click(timeout=5000)
        page.keyboard.insert_text(message)
        page.wait_for_timeout(600)
        if (box.inner_text() or "").strip():
            return True
        log("insert_text 未生效，尝试剪贴板粘贴。")
        page.evaluate(
            """(text) => {
                const el = document.querySelector('[contenteditable="true"]') || document.querySelector('[data-block-id]');
                el.focus();
                const dt = new DataTransfer();
                dt.setData('text/plain', text);
                el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
            }""",
            message,
        )
        page.wait_for_timeout(600)
        return bool((box.inner_text() or "").strip())
    except Exception as exc:
        log(f"写入文字失败：{exc}")
        return False


def editor_text(page: Page) -> str:
    box = first_visible(page, INPUT_SELECTORS)
    if box is None:
        return ""
    try:
        return (box.inner_text() or "").replace("\u200b", "").strip()
    except Exception:
        return ""


def click_send(page: Page) -> bool:
    box = first_visible(page, SEND_SELECTORS)
    if box is None:
        return False
    try:
        box.click(timeout=4000)
        return True
    except Exception as exc:
        log(f"点击发送按钮失败：{exc}")
        return False


def send_to(page: Page, target: str, message: str, dry_run: bool = False) -> str:
    """返回 ok / dry-run / rate_limited / failed。"""
    if not open_chat(page, target):
        return "failed"
    if rate_limited(page):
        return "rate_limited"

    if not type_message(page, message):
        dump_debug(page, "cant-type")
        return "failed"

    if dry_run:
        try:
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
        except Exception:
            pass
        log(f"[演练] “{target}” 会话可定位、输入框可用，未发送。")
        return "dry-run"

    before = editor_text(page)
    if not click_send(page):
        page.keyboard.press("Enter")          # 兼容旧版：回车发送
    page.wait_for_timeout(2500)

    if rate_limited(page):
        return "rate_limited"
    if before and editor_text(page) != before:   # 文字离开输入框 = 已发出
        log(f"已发送给“{target}”：{message}")
        return "ok"

    dump_debug(page, "send-failed")
    return "failed"


def run_once(cfg: dict, dry_run: bool = False, targets=None) -> list[str]:
    """对目标各发一条，返回未成功的昵称列表（供补发使用）。"""
    queue = list(targets if targets is not None else cfg["targets"])
    failed: list[str] = []
    with sync_playwright() as pw:
        ctx = launch(pw, headless=bool(cfg.get("headless", True)) and not dry_run)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for idx, target in enumerate(queue):
            message = random.choice(cfg["messages"])
            status = send_to(page, target, message, dry_run=dry_run)
            if status == "rate_limited":
                log("检测到“操作频繁 / 安全验证”，本轮立即停止，避免加重风控。")
                failed.extend(queue[idx:])      # 未轮到的也留待补发
                break
            if status == "failed":
                failed.append(target)
            time.sleep(random.uniform(cfg.get("min_delay_seconds", 2), cfg.get("max_delay_seconds", 6)))
        ctx.close()
    return failed


def retry_later(cfg: dict, failed: list[str]) -> list[str]:
    """仅对未成功的目标补发一次。"""
    if not failed:
        return []
    log(f"未成功：{failed}；45 分钟后补发一次。")
    time.sleep(45 * 60)
    return run_once(cfg, targets=failed)


def list_conversations(cfg: dict) -> None:
    with sync_playwright() as pw:
        ctx = launch(pw, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(CHAT_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        if not is_logged_in(page):
            log("未登录，请先运行 login.py。")
        else:
            for sel in LIST_SELECTORS:
                loc = page.locator(sel)
                try:
                    n = min(loc.count(), 40)
                except Exception:
                    continue
                names = []
                for i in range(n):
                    try:
                        t = (loc.nth(i).inner_text() or "").strip().splitlines()
                        if t:
                            names.append(t[0])
                    except Exception:
                        continue
                if names:
                    log(f"会话列表（{sel}）：")
                    for nm in names:
                        print("   ", nm)
                    break
            else:
                log("未能自动解析会话列表，请肉眼查看弹出的窗口。")
                page.wait_for_timeout(60000)
        ctx.close()


def sleep_until(cfg: dict) -> None:
    now = _dt.datetime.now()
    target = now.replace(hour=cfg.get("hour", 9), minute=cfg.get("minute", 0), second=0, microsecond=0)
    if target <= now:
        target += _dt.timedelta(days=1)
    target += _dt.timedelta(minutes=random.randint(0, cfg.get("jitter_minutes", 0)))
    wait = (target - now).total_seconds()
    log(f"下次发送时间：{target:%Y-%m-%d %H:%M}（等待 {wait/3600:.2f} 小时）")
    time.sleep(wait)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="执行一轮后退出（供计划任务调用）")
    ap.add_argument("--now", action="store_true", help="立即发送一轮")
    ap.add_argument("--dry-run", action="store_true", help="演练，不真正发送")
    ap.add_argument("--list", action="store_true", help="列出会话，确认好友昵称")
    args = ap.parse_args()

    cfg = load_config_or_alert()
    if cfg is None:
        sys.exit(1)

    if args.list:
        list_conversations(cfg)
        return

    if args.dry_run:
        sys.exit(1 if run_once(cfg, dry_run=True) else 0)

    if args.now:
        sys.exit(1 if retry_later(cfg, run_once(cfg)) else 0)

    if args.once:                      # 供计划任务调用
        jitter = int(cfg.get("jitter_minutes", 0))
        if jitter:
            delay = random.randint(0, jitter) * 60
            log(f"随机延迟 {delay // 60} 分钟后发送。")
            time.sleep(delay)
        sys.exit(1 if retry_later(cfg, run_once(cfg)) else 0)

    while True:                       # 常驻：每天定时发送，失败自动补发
        sleep_until(cfg)
        retry_later(cfg, run_once(cfg))
        time.sleep(60)


if __name__ == "__main__":
    main()
