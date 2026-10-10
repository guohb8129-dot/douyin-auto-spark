# 一键安装：检查环境 -> 建虚拟环境 -> 装依赖 -> 生成配置。
# 用法： powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host '=== 抖音续火花 · 环境检查 ===' -ForegroundColor Cyan

# 1) Python：Windows 上 `python` 可能是应用商店占位程序，必须实测能否用。
$py = $null
foreach ($cand in @('py', 'python', 'python3')) {
    $cmd = Get-Command $cand -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    & $cmd.Source -c 'import venv' 2>$null
    if ($LASTEXITCODE -eq 0) { $py = $cmd.Source; break }
}
if (-not $py) {
    throw '未找到可用的 Python。请从 https://www.python.org/downloads/ 安装（安装时勾选 Add python.exe to PATH），再重新运行本脚本。若已装但仍报此错，说明 PATH 里的 python 是应用商店占位程序，请在“设置 > 应用 > 高级应用设置 > 应用执行别名”中关闭它。'
}
Write-Host "[OK] Python: $py"

# 2) Chrome
$chrome = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($chrome) { Write-Host "[OK] Chrome: $chrome" }
else { Write-Warning '未检测到 Google Chrome。请先安装 Chrome，否则无法登录与发送。' }

# 3) 虚拟环境与依赖
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    Write-Host '[..] 创建虚拟环境 .venv' -ForegroundColor Yellow
    & $py -m venv .venv
}
Write-Host '[..] 安装依赖（首次约需 1-2 分钟）' -ForegroundColor Yellow
& '.venv\Scripts\python.exe' -m pip install --upgrade pip -q
& '.venv\Scripts\python.exe' -m pip install -r requirements.txt -q
Write-Host '[OK] 依赖安装完成'

# 4) 生成配置
if (-not (Test-Path 'config.json')) {
    Copy-Item 'config.example.json' 'config.json'
    Write-Host '[OK] 已生成 config.json' -ForegroundColor Green
} else {
    Write-Host '[OK] 已存在 config.json，未覆盖'
}

Write-Host ''
Write-Host '=== 接下来三步 ===' -ForegroundColor Cyan
Write-Host '1. 编辑 config.json：targets 填好友昵称，hour/minute 填发送时间'
Write-Host '     notepad config.json'
Write-Host '2. 扫码登录（弹出的 Chrome 里用抖音 App 扫）：'
Write-Host '     .venv\Scripts\python.exe login.py'
Write-Host '3. 演练，确认能找到会话但不会真的发送：'
Write-Host '     .venv\Scripts\python.exe spark.py --dry-run'
Write-Host '   演练通过后真发一轮：'
Write-Host '     .venv\Scripts\python.exe spark.py --now'
Write-Host '4. 设为每天自动运行：'
Write-Host '     powershell -ExecutionPolicy Bypass -File install_task.ps1'
