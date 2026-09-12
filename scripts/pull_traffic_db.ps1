<#
Pulls data/traffic.db from the EC2 collector VM down to this laptop.
Meant to be run hourly via Windows Task Scheduler (see scripts/register_hourly_pull.ps1).

Overwrites the local "live" copy AND keeps a timestamped snapshot in data/backups/,
so a bad pull (or a VM problem) never destroys the previous good copy.
#>

# ---- EDIT THESE TWO LINES ----
$VmIp   = "3.26.40.182"          # e.g. "3.26.40.182"
$KeyPath = "$HOME\.ssh\traffic-analytics.pem"        # path to whichever key connects you to the VM
# --------------------------------

$RemoteUser   = "ubuntu"
$RemoteDbPath = "~/Intelligent-Traffic-Analytics/data/traffic.db"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LocalLive   = Join-Path $ProjectRoot "data\traffic.db"
$BackupDir   = Join-Path $ProjectRoot "data\backups"
$LogFile     = Join-Path $ProjectRoot "scripts\pull_log.txt"

$Timestamp   = Get-Date -Format "yyyy-MM-dd_HHmm"
$BackupPath  = Join-Path $BackupDir "traffic_$Timestamp.db"

if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}

function Write-Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg"
    Add-Content -Path $LogFile -Value $line
}



# Pull straight to the timestamped backup slot first...
& scp.exe -i $KeyPath -o ConnectTimeout=15 "$RemoteUser@${VmIp}:$RemoteDbPath" $BackupPath 2>> $LogFile

if ($LASTEXITCODE -eq 0 -and (Test-Path $BackupPath)) {
    # ...then promote it to the "live" copy once we know the transfer succeeded.
    Copy-Item -Path $BackupPath -Destination $LocalLive -Force
    $sizeKb = [math]::Round((Get-Item $BackupPath).Length / 1KB, 1)
    Write-Log "OK: pulled traffic.db ($sizeKb KB) -> $BackupPath and updated $LocalLive"
} else {
    Write-Log "FAILED: scp exit code $LASTEXITCODE -- see above for stderr"
    if (Test-Path $BackupPath) { Remove-Item $BackupPath -Force }
}



