<#
Registers (or re-registers) the hourly Windows Task Scheduler job that runs
pull_traffic_db.ps1. Run this once, from an ordinary PowerShell window
(no admin needed for a per-user task).
#>

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ScriptPath  = Join-Path $ProjectRoot "scripts\pull_traffic_db.ps1"
$TaskName    = "TrafficDB_HourlyPull"

$Action  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)

$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Hourly pull of traffic.db from the EC2 collector VM" -Force

Write-Host "Registered '$TaskName'. It will run hourly, and will fire on wake/logon if a scheduled run was missed (StartWhenAvailable)."
Write-Host "Test it immediately with:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Then check:  Get-Content `"$ProjectRoot\scripts\pull_log.txt`" -Tail 5"

