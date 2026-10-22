<#
Runs one FIO job file N times and saves each run as JSON in results/raw.
Also appends one line per run to results/raw/run_log.csv.

Usage (from the repo root):
  powershell -ExecutionPolicy Bypass -File scripts\run_job.ps1 -Job jobs\02_qd1_baselines.fio -Reps 3
#>
param(
    [Parameter(Mandatory = $true)][string]$Job,
    [int]$Reps = 3,
    [int]$CooldownSec = 30
)

$ErrorActionPreference = "Stop"
$Root    = Split-Path -Parent $PSScriptRoot
$JobPath = Resolve-Path $Job
$JobName = [IO.Path]::GetFileNameWithoutExtension($JobPath)
$RawDir  = Join-Path $Root "results\raw"
$LogCsv  = Join-Path $RawDir "run_log.csv"
New-Item -ItemType Directory -Path $RawDir -Force | Out-Null

if (-not (Get-Command fio -ErrorAction SilentlyContinue)) {
    throw "fio not found on PATH"
}
if ($JobName -ne "00_prep" -and -not (Test-Path "C:\fiotest\testfile")) {
    throw "C:\fiotest\testfile does not exist. Run jobs\00_prep.fio first."
}
if (-not (Test-Path $LogCsv)) {
    "job,rep,start,end,output_file,power_status" | Out-File $LogCsv -Encoding ascii
}

$FioVersion = (fio --version)
for ($i = 1; $i -le $Reps; $i++) {
    $Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $Out   = Join-Path $RawDir "${JobName}_${Stamp}_r${i}.json"
    $Power = (Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue).BatteryStatus
    $Start = Get-Date -Format "o"
    Write-Host "[$JobName] rep $i/$Reps -> $Out"
    fio $JobPath --output-format=json --output=$Out
    if ($LASTEXITCODE -ne 0) { throw "fio exited with code $LASTEXITCODE" }
    $End = Get-Date -Format "o"
    "$JobName,$i,$Start,$End,$(Split-Path $Out -Leaf),$Power" | Out-File $LogCsv -Append -Encoding ascii
    if ($i -lt $Reps) {
        Write-Host "  cooling down ${CooldownSec}s..."
        Start-Sleep -Seconds $CooldownSec
    }
}
Write-Host "Done. $FioVersion"
