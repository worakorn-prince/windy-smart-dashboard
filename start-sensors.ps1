# start-sensors.ps1 — Launch LibreHardwareMonitor (elevated, single instance)
# so the dashboard can read CPU/RAM/GPU/disk temperatures via WMI.
#
# Usage:
#   powershell -File start-sensors.ps1          # start & verify
#   powershell -File start-sensors.ps1 -Verify  # only verify current state

param([switch]$Verify)

$ErrorActionPreference = "SilentlyContinue"
$lhmName = "LibreHardwareMonitor"

function Find-LhmExe {
    # 1) winget portable package location
    $p = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" `
            -Filter "LibreHardwareMonitor.exe" -Recurse -ErrorAction SilentlyContinue |
          Select-Object -First 1 -ExpandProperty FullName
    if ($p) { return $p }
    # 2) Program Files (installer variant)
    foreach ($d in @("$env:ProgramFiles\LibreHardwareMonitor", "${env:ProgramFiles(x86)}\LibreHardwareMonitor")) {
        $p = Join-Path $d "LibreHardwareMonitor.exe"
        if (Test-Path $p) { return $p }
    }
    # 3) PATH alias
    return (Get-Command LibreHardwareMonitor -ErrorAction SilentlyContinue).Source
}

function Test-WmiSensors {
    try {
        $s = Get-CimInstance -Namespace "root\LibreHardwareMonitor" -ClassName Sensor `
               -ErrorAction Stop
        return @($s)
    } catch { return @() }
}

if (-not $Verify) {
    # Close every existing instance first — two copies fight over the driver.
    $running = Get-Process -Name $lhmName -ErrorAction SilentlyContinue
    if ($running) {
        Write-Host "[sensors] Closing $($running.Count) existing LibreHardwareMonitor window(s)..." -ForegroundColor Yellow
        $running | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        if (Get-Process -Name $lhmName -ErrorAction SilentlyContinue) {
            Write-Host "[sensors] Could not kill some instances - please close LibreHardwareMonitor windows manually." -ForegroundColor Red
        }
    }

    $exe = Find-LhmExe
    if (-not $exe) {
        Write-Host "[sensors] Not found. Install with:" -ForegroundColor Red
        Write-Host '           winget install -e --id LibreHardwareMonitor.LibreHardwareMonitor' -ForegroundColor Cyan
        exit 1
    }

    Write-Host "[sensors] Launching (accept the UAC prompt): $exe"
    Start-Process -FilePath $exe -Verb RunAs
    Write-Host "[sensors] Waiting for sensors..."
    Start-Sleep -Seconds 8
}

# --- Verify ---
$deadline = (Get-Date).AddSeconds(25)
while ((Get-Date) -lt $deadline) {
    $sensors = Test-WmiSensors
    if ($sensors.Count -gt 0) { break }
    Start-Sleep -Seconds 2
}

$sensors = Test-WmiSensors
if ($sensors.Count -eq 0) {
    Write-Host "[sensors] FAIL: no WMI sensors found." -ForegroundColor Red
    Write-Host "  Checklist:"
    Write-Host "   1. Only ONE LibreHardwareMonitor window is open."
    Write-Host "   2. It was started as Administrator (UAC accepted)."
    Write-Host "   3. Its main tree shows temperatures (CPU/GPU sections)."
    exit 1
}

Write-Host "[sensors] OK - $($sensors.Count) sensors published." -ForegroundColor Green
$sensors | Where-Object SensorType -eq 'Temperature' |
    Select-Object -First 8 Name, Value, Parent | Format-Table -AutoSize
