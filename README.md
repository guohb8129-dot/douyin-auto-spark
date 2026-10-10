# douyin-auto-spark · 抖音自动续火花

每天定时用**抖音网页版**给指定好友发一条消息，保持聊天火花不熄灭。
基于 Playwright + 你本机的真实 Chrome，登录态本地保存，日常无人值守。

> 原理：抖音网页版（`douyin.com/chat`）支持私信，网页端发出的消息同样计入火花。
> 脚本用真实 Chrome 打开聊天页，定位目标会话，写入并发送消息。

## 功能

- 每天固定时间自动发送，时间带随机抖动，避免分秒不差
- 支持多个好友，消息从模板池随机选取
- 发送前校验会话标题，杜绝「发给上一个人」
- 检测到「操作频繁 / 安全验证」立即停止本轮，避免加重风控
- 失败约 45 分钟后自动补发一次
- 登录态失效时写桌面告警文件并弹 Windows 通知
- 全程无需自建服务器，Windows 计划任务驱动

## 环境要求

- Windows 10/11
- Python 3.9+
- Google Chrome

## 快速开始

```powershell
# 1. 一键安装：检查环境、建虚拟环境、装依赖、生成配置
powershell -ExecutionPolicy Bypass -File setup.ps1

# 2. 编辑配置：填好友昵称与发送时间
notepad config.json

# 3. 扫码登录（弹出的 Chrome 里用抖音 App 扫一扫）
.venv\Scripts\python.exe login.py

# 4. 演练：确认能找到会话，但不会真的发送
.venv\Scripts\python.exe spark.py --dry-run

# 5. 真发一轮
.venv\Scripts\python.exe spark.py --now

# 6. 设为每天自动运行
powershell -ExecutionPolicy Bypass -File install_task.ps1
```

## 配置说明 `config.json`

| 字段 | 说明 |
| --- | --- |
| `targets` | 好友昵称数组，须与聊天列表显示的名字完全一致（含标点） |
| `messages` | 消息池，每次随机挑一条 |
| `hour` / `minute` | 每天发送时间（24 小时制） |
| `jitter_minutes` | 随机延迟分钟数 |
| `headless` | `true` 后台静默运行，`false` 显示窗口便于排查 |
| `min_delay_seconds` / `max_delay_seconds` | 多个好友之间的随机间隔 |

不确定好友昵称时，用 `spark.py --list` 打印会话列表核对。

## 命令行

| 命令 | 作用 |
| --- | --- |
| `spark.py` | 常驻模式，每天定时发送 |
| `spark.py --once` | 执行一轮后退出（计划任务用这个） |
| `spark.py --now` | 立即发送一轮 |
| `spark.py --dry-run` | 演练，不真正发送 |
| `spark.py --list` | 列出会话，确认昵称 |
| `login.py` | 扫码登录 / 刷新登录态 |

## 目录结构

```
common.py            浏览器启动、登录态判定、日志、告警
login.py             一次性扫码登录
spark.py             定时发送主程序
probe.py             私信页 DOM 探测（改版排查用）
config.example.json  配置模板
setup.ps1            一键安装
install_task.ps1     注册 Windows 每日计划任务
run.bat              常驻运行
profile/             登录态（自动生成，切勿分享）
logs/                运行日志与失败现场（自动生成）
```

## 维护

以下选择器在 2026-10 的抖音网页版上实测确认，抖音改版后可能失效：

| 用途 | 选择器 |
| --- | --- |
| 输入框 | `[contenteditable="true"]`（`data-placeholder="发送消息"`） |
| 发送按钮 | `.e2e-send-msg-btn` |
| 会话标题 | `.RightPanelHeadertitle` |

定位失败时 `logs/` 会保存现场截图与 HTML，据此更新 `spark.py` 顶部的
`INPUT_SELECTORS` / `SEND_SELECTORS` / `HEADER_SELECTORS`。

也可以直接跑探测脚本，打印当前页面的真实结构：

```powershell
.venv\Scripts\python.exe probe.py
```

## 常见问题

**登录态多久过期？**
通常几周。失效时会主动提醒（桌面文件 + 系统通知），重新跑 `login.py` 扫码即可。

**电脑关机时会发送吗？**
不会。计划任务在关机/睡眠时不执行，睡眠唤醒后 Windows 会补跑当天错过的任务。
需要 7×24 稳定的话，可放到一台常开的机器或云服务器上。

**能保证火花不断吗？**
火花要求**双方**当天都发过消息。本工具保证你这一半不漏发，对方那一半无法代劳。

**消息真发出去了吗？**
判定标准是文字离开输入框。失败会写日志并保存现场截图，供排查。

## 免责声明

自动化发私信不符合抖音社区公约，存在被限流、触发安全验证乃至封号的风险。
请仅用于本人账号、少量好友、每天一条的低频场景，并自行承担后果。
`profile/` 目录包含账号登录态，等同于账号凭证，**切勿分享或提交到仓库**。

## License

[MIT](LICENSE)
