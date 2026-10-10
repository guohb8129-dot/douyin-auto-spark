"""一次性扫码登录。

登录态保存在 profile/ 目录，之后 spark.py 直接复用；一般可维持数周，
过期后重新运行本脚本扫一次即可。
"""
from playwright.sync_api import sync_playwright

from common import CHAT_URL, clear_login_alert, is_logged_in, launch, log

WAIT_ATTEMPTS = 120   # 120 * 5s = 10 分钟


def main() -> None:
    with sync_playwright() as pw:
        ctx = launch(pw, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(CHAT_URL, wait_until="domcontentloaded")

        if is_logged_in(page):
            log("检测到已登录，无需重新扫码。")
            clear_login_alert()
            ctx.close()
            return

        log("请在弹出的 Chrome 窗口里用抖音 App 扫码登录，等待中（最多 10 分钟）…")
        for _ in range(WAIT_ATTEMPTS):
            if is_logged_in(page):
                page.wait_for_timeout(3000)   # 等登录后跳转稳定
                clear_login_alert()
                log("登录成功，登录态已保存。接下来可运行 spark.py。")
                break
            page.wait_for_timeout(5000)
        else:
            log("等待登录超时，请重新运行 login.py。")
        ctx.close()


if __name__ == "__main__":
    main()
