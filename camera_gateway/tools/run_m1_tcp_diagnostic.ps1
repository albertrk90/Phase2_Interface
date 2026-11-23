<#
O1/O2 diagnostic wrapper (approved 13 Nov 2026). Runs the UNCHANGED Stage 2 runner (default M1 preview,
-NetworkScope EthernetScoped, 120 s gateway limit, keyint 20, 150 ms age guard, resync) and, alongside it:
  - tools\tcp_counter_sampler.py   read-only system-wide TCP counters every 10 ms (started before the runner)
  - tools\camera_ping_watch.py     1 Hz ICMP to Camera A only, from GATEWAY_STOP until the runner has finished
Nothing in the runner, gateway, MediaMTX config or Unity player is changed or passed different arguments.
Output: camera_gateway\results\m1_tcp_diag_<stamp>\ (diag_status.json links the runner folder).
#>
param([switch]$PlanOnly)
$ErrorActionPreference = "Stop"
$gw = Split-Path -Parent $PSScriptRoot
$res = Join-Path $gw "results"
$py = Join-Path $gw ".venv\Scripts\python.exe"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$diag = Join-Path $res "m1_tcp_diag_$stamp"
New-Item -ItemType Directory -Force $diag | Out-Null
$stop = Join-Path $diag "SAMPLER_STOP"
$runnerArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "run_stage2.ps1"), "-NetworkScope", "EthernetScoped")
if ($PlanOnly) { $runnerArgs += "-PlanOnly" }
$st = [ordered]@{ started = (Get-Date).ToString("o"); runner_args = ($runnerArgs[4..($runnerArgs.Count - 1)] -join " "); plan_only = [bool]$PlanOnly }
$sampler = Start-Process -FilePath $py -ArgumentList @("-I", (Join-Path $PSScriptRoot "tcp_counter_sampler.py"), "--out", (Join-Path $diag "tcp_counters.csv"), "--interval-ms", "10", "--stop-file", $stop, "--max-seconds", "600") -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $diag "sampler_stdout.txt") -RedirectStandardError (Join-Path $diag "sampler_stderr.txt")
$pinger = $null
if (-not $PlanOnly) {
    $pinger = Start-Process -FilePath $py -ArgumentList @("-I", (Join-Path $PSScriptRoot "camera_ping_watch.py"), "--results", $res, "--out", (Join-Path $diag "camera_ping.csv"), "--max-seconds", "300") -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $diag "ping_stdout.txt") -RedirectStandardError (Join-Path $diag "ping_stderr.txt")
}
Start-Sleep -Seconds 5      # 5 s of in-situ pre-run baseline before anything is launched
try {
    $before = @(Get-ChildItem $res -Directory -Filter "stage2_runner_*" | ForEach-Object { $_.Name })
    & powershell @runnerArgs
    $st.runner_exit_code = $LASTEXITCODE
    $new = Get-ChildItem $res -Directory -Filter "stage2_runner_*" | Where-Object { $before -notcontains $_.Name } | Sort-Object Name | Select-Object -Last 1
    $st.runner_dir = if ($new) { $new.FullName } else { $null }
} finally {
    Start-Sleep -Seconds 5  # 5 s of post-run baseline
    New-Item -ItemType File -Force $stop | Out-Null
    if (-not $sampler.WaitForExit(15000)) { $sampler.Kill(); $st.sampler_killed = $true }
    if ($pinger -and -not $pinger.WaitForExit(30000)) { $pinger.Kill(); $st.pinger_killed = $true }
    $st.finished = (Get-Date).ToString("o")
    $st | ConvertTo-Json -Depth 3 | Out-File -Encoding utf8 (Join-Path $diag "diag_status.json")
}
Get-Content (Join-Path $diag "diag_status.json")
