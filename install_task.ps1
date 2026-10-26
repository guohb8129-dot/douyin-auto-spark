# 注册 Windows 每日计划任务（开机/唤醒后错过的当天任务会自动补跑）。
# 项目目录移动后必须重跑本脚本，否则任务仍指向旧路径、启动即失败。
#   用法： powershell -ExecutionPolicy Bypass -File install_task.ps1
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# Windows PowerShell 5.1 默认按 GBK 读文件，这里显式指定 UTF-8，避免消息里的 emoji 被弄乱。
$cfgText = [System.IO.File]::ReadAllText((Join-Path $root 'config.json'), [System.Text.UTF8Encoding]::new($false))
$cfg = $cfgText | ConvertFrom-Json

$python = Join-Path $root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $python)) { $python = Join-Path $root '.venv\Scripts\python.exe' }
if (-not (Test-Path $python)) { throw '未找到 .venv，请先按 README 创建虚拟环境。' }

$script = Join-Path $root 'spark.py'
if (-not (Test-Path $script)) { throw "未找到 spark.py：$script" }

$taskName = 'DouyinSpark'
$action   = New-ScheduledTaskAction -Execute $python -Argument 'spark.py --once' -WorkingDirectory $root
$trigger  = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours($cfg.hour).AddMinutes($cfg.minute))
# 超时放宽到 2 小时，容纳 jitter 与 45 分钟后的失败补发。
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 120)

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Description '每天定时给抖音好友发私信续火花' | Out-Null

# 注册后回读并校验，确认任务指向的文件真实存在。
$registered = (Get-ScheduledTask -TaskName $taskName).Actions[0]
if (-not (Test-Path $registered.Execute)) {
    throw "任务已注册但执行路径不存在：$($registered.Execute)"
}

Write-Host "已注册计划任务 $taskName，每天 $($cfg.hour):$($cfg.minute) 运行。"
Write-Host "执行文件：$($registered.Execute)"
Write-Host "工作目录：$($registered.WorkingDirectory)"
Write-Host "查看： Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo"
Write-Host "删除： Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"