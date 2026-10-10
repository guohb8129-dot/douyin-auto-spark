# 注册 Windows 每日计划任务（开机/唤醒后错过的当天任务会自动补跑）。
# 在项目目录下执行： powershell -ExecutionPolicy Bypass -File install_task.ps1
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
# Windows PowerShell 5.1 默认按 GBK 读文件，这里显式指定 UTF-8，避免消息里的 emoji 被弄乱。
$cfgText = [System.IO.File]::ReadAllText((Join-Path $root 'config.json'), [System.Text.UTF8Encoding]::new($false))
$cfg = $cfgText | ConvertFrom-Json

$python = Join-Path $root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $python)) { $python = Join-Path $root '.venv\Scripts\python.exe' }
if (-not (Test-Path $python)) { throw "未找到 .venv，请先按 README 创建虚拟环境。" }

$taskName = 'DouyinSpark'
$action   = New-ScheduledTaskAction -Execute $python -Argument 'spark.py --once' -WorkingDirectory $root
$trigger  = New-ScheduledTaskTrigger -Daily -At ([datetime]::Today.AddHours($cfg.hour).AddMinutes($cfg.minute))
# 超时放宽到 2 小时，容纳 jitter 与 45 分钟后的失败补发。
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 120)

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Description '每天定时给抖音好友发私信续火花' | Out-Null

Write-Host "已注册计划任务 $taskName，每天 $($cfg.hour):$($cfg.minute) 运行。"
Write-Host "查看： Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo"
Write-Host "删除： Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"
