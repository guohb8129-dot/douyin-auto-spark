"""抖音网页版私信页 DOM 探测工具。

抖音改版导致发送失败时，用它打印聊天页的真实结构，
据此更新 spark.py 顶部的 INPUT_SELECTORS / SEND_SELECTORS / HEADER_SELECTORS。

用法：
    python probe.py            # 打印输入框、发送按钮、会话标题
    python probe.py --html     # 同时把完整 HTML 存到 logs/ 供细查
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from common import CHAT_URL, LOG_DIR, is_logged_in, launch

JS = """() => {
  const pick = (el, extra = {}) => Object.assign({
    tag: el.tagName,
    cls: (el.className || '').toString().slice(0, 120),
    text: (el.innerText || '').trim().slice(0, 40),
    testid: el.getAttribute('data-e2e') || el.getAttribute('data-testid') || '',
  }, extra);
  return {
    url: location.href,
    logged_in_hint: location.pathname,
    editor: [...document.querySelectorAll('[contenteditable="true"]')]
      .map(e => pick(e, {placeholder: e.getAttribute('data-placeholder') || ''})),
    send_candidates: [...document.querySelectorAll('[class*="publishBtn"],[class*="send"]')]
      .map(e => pick(e)),
    headers: [...document.querySelectorAll('[class*="convHeader"],[class*="RightPanelHeade"]')]
      .map(e => pick(e)),
    search_inputs: [...document.querySelectorAll('input')]
      .map(e => pick(e, {placeholder: e.placeholder || ''})),
  };
}"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", action="store_true", help="同时保存完整 HTML")
    args = ap.parse_args()

    with sync_playwright() as pw:
        ctx = launch(pw, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)
        print("已登录:", is_logged_in(page))
        print(json.dumps(page.evaluate(JS), ensure_ascii=False, indent=2))
        if args.html:
            LOG_DIR.mkdir(exist_ok=True)
            out = LOG_DIR / "chat-page.html"
            out.write_text(page.content(), encoding="utf-8")
            print("HTML 已保存：", out)
        ctx.close()


if __name__ == "__main__":
    main()
