<#
O1 connection-specific ETW diagnostic (13 Nov 2026). Instructions: camera_gateway/O1_ETW_CAPTURE_INSTRUCTIONS.md.
Built-in Windows ETW only; nothing installed; no system / security setting changed. Raw traces stay local (retained by default).

MODES
  -Feasibility   (run 13 Nov 18:39) ~10 s local self-test, no camera.
  camera mode    (default; approved 13 Nov: ONE capture around the existing 60 s M1 preview, Camera A only):
                   1  start the UNCHANGED runner: run_stage2.ps1 -NetworkScope Isolated -TraceHandshakeDir <out>\handshake
                      (gateway 120 s default limit, keyint 20, 150 ms, resync, M1 60 s preview: all unchanged)
                   2  wait until the runner reports READY_FOR_TRACE (camera, MediaMTX and gateway streaming; player NOT launched yet)
                   3  start tracing (2 GB cap, SEQUENTIAL file: nothing at the beginning is ever overwritten; if the cap is reached,
                      later events are dropped and counted as lost), write the START alignment marker, then TRACE_STARTED
                      -> the runner launches the M1 player, whose reader connections are therefore traced from their creation
                   4  stop when the runner reports PREVIEW_DONE (+3 s tail), or at the HARD deadline of 120 s after the trace
                      started, whichever is first; the END marker is written just before the stop. The post-run reconnect (O2)
                      happens after the stop and is not traced.
                   5  wait for the runner's orderly shutdown (bounded; abort file if it overruns)
                 Cleanup: the trace session is stopped on success, on the deadline, on a runner failure and on any error (trap).
  -Simulate      OFFLINE orchestration test of camera mode: runner -DryRun (fake MediaMTX / gateway / player), NO tracing (logman is
                 not called), no elevation or isolation needed. -SimFault none|gateway_abort|unity_hang|wrapper_error.

COLLECTION (provider + keyword mask + level only; system-wide kernel providers: no port / process filter exists at collection)
  Microsoft-Windows-TCPIP 0x0000010300400104 level 5 ; Microsoft-Windows-Winsock-AFD 0x000000000000000E level 5 ; clock QPC (-ct perf)
  Unrelated local metadata (other connections and processes, and rundown records of connections that existed at session start, which
  can include external ones) is collected and is excluded only in post-processing.
RETENTION  raw\o1.etl retained locally with SHA-256 until validated extraction and the researcher's decision; never uploaded.
#>
param([switch]$Armed, [switch]$Feasibility, [switch]$Simulate, [ValidateSet("none", "gateway_abort", "unity_hang", "wrapper_error")][string]$SimFault = "none",
      [int]$SimPreviewSeconds = 15, [int]$MaxSeconds = 120, [int]$MaxMB = 2048, [switch]$DeleteRawAfterValidation,
      [string]$Out = "", [int]$WaitForIsolationMinutes = 0, [switch]$PauseAtEnd)
$ErrorActionPreference = "Stop"
$gw = Split-Path -Parent $PSScriptRoot
$py = Join-Path $gw ".venv\Scripts\python.exe"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$mode = if ($Feasibility) { "feasibility" } elseif ($Simulate) { "simulate" } else { "capture" }
$out = if ($Out) { $Out } else { Join-Path $gw "results\o1_etw_${mode}_$stamp" }
$raw = Join-Path $out "raw"; $hs = Join-Path $out "handshake"
$session = "Phase2_O1_Loopback"
$providers = @('"Microsoft-Windows-TCPIP" 0x0000010300400104 0x5', '"Microsoft-Windows-Winsock-AFD" 0x000000000000000E 0x5')
$MaxSeconds = [Math]::Max(10, [Math]::Min($MaxSeconds, 120))           # hard tracing deadline (approved: 120 s)
$MaxMB = [Math]::Max(64, [Math]::Min($MaxMB, 2048))                    # approved cap: 2 GB
$WaitForIsolationMinutes = [Math]::Max(0, [Math]::Min($WaitForIsolationMinutes, 30))
$ReadyTimeoutS = 420; $RunnerShutdownS = 360; $TailS = 3

function NonLinkLocal {   # the validated runner's rule: host-name IPv4 addresses (interfaces that are up) must all be link-local
    $a = @(& $py -I -c "import socket;print(chr(10).join(sorted({i[4][0] for i in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET)})))" 2>$null | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' })
    @($a | Where-Object { $_ -notlike "127.*" -and $_ -notlike "169.254.*" })
}
function Heartbeat($state) { try { [ordered]@{ t = (Get-Date).ToString("o"); state = $state } | ConvertTo-Json -Compress | Out-File -Encoding utf8 (Join-Path $out "status.json") } catch {} }
function DisableQuickEdit {   # this console only: a click would otherwise suspend the script at its next output
    try {
        Add-Type -Namespace P2 -Name Con -MemberDefinition '[DllImport("kernel32.dll")] public static extern System.IntPtr GetStdHandle(int h); [DllImport("kernel32.dll")] public static extern bool GetConsoleMode(System.IntPtr h, out uint m); [DllImport("kernel32.dll")] public static extern bool SetConsoleMode(System.IntPtr h, uint m);' -ErrorAction Stop
        $h = [P2.Con]::GetStdHandle(-10); $m = 0
        if ([P2.Con]::GetConsoleMode($h, [ref]$m)) { [void][P2.Con]::SetConsoleMode($h, (($m -band (-bnot 0x40)) -bor 0x80)) }
    } catch {}
}
function EndPause { if ($PauseAtEnd) { Read-Host "Press Enter to close this window" | Out-Null } }
function SessionExists { @(logman query -ets 2>$null | Select-String $session).Count -gt 0 }
function StartTrace {
    if ($Simulate) { "SIMULATED: logman not called" | Out-File -Encoding utf8 (Join-Path $out "logman_start.txt"); return }
    $a = @("create", "trace", $session, "-ets", "-o", (Join-Path $raw "o1.etl"), "-ct", "perf", "-bs", "1024", "-nb", "64", "512", "-max", "$MaxMB", "-pf", (Join-Path $out "providers.txt"))
    if ($Feasibility) { $a += @("-mode", "Circular") }    # as run at the feasibility step
    & logman @a | Out-File -Encoding utf8 (Join-Path $out "logman_start.txt")
    if (-not (SessionExists)) { throw "trace session did not start (see logman_start.txt)" }
}
function QuerySession { if (-not $Simulate) { & logman query $session -ets 2>&1 | Out-File -Encoding utf8 (Join-Path $out "logman_query_before_stop.txt") } }
function StopTrace { if ($Simulate) { "SIMULATED" | Out-File -Encoding utf8 (Join-Path $out "logman_stop.txt"); return }; if (SessionExists) { & logman stop $session -ets | Out-File -Encoding utf8 (Join-Path $out "logman_stop.txt") } }
function Marker($label) { & $py -I (Join-Path $PSScriptRoot "o1_etw_marker.py") --label $label --out (Join-Path $out "marker_$label.json") | Out-Null }

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$admin = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$perfLog = @($id.Groups | Where-Object { $_.Value -eq "S-1-5-32-559" }).Count -gt 0
$elevated = $admin -or $perfLog
$nonLinkLocal = NonLinkLocal; $isolated = $nonLinkLocal.Count -eq 0
$runnerArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$PSScriptRoot\run_stage2.ps1`" -NetworkScope Isolated -TraceHandshakeDir `"$hs`"" +
              $(if ($Simulate) { " -DryRun -PreviewSeconds $SimPreviewSeconds" + $(if ($SimFault -in "gateway_abort", "unity_hang") { " -Fault $SimFault" } else { "" }) } else { "" })
$plan = [ordered]@{
    mode = $mode; tracing_rights = [ordered]@{ administrator = $admin; performance_log_users = $perfLog }; isolated = $isolated; non_link_local_ipv4 = $nonLinkLocal; output = $out
    collection = [ordered]@{ providers = $providers; clock = "QPC (-ct perf)"; file = $(if ($Feasibility) { "circular" } else { "sequential (beginning never overwritten; events lost if the cap is reached)" }); cap_mb = $MaxMB
                            port_or_process_filter_at_collection = "none available (system-wide kernel providers)"; payload = "not requested (Packet keyword off)" }
    ordering = $(if ($Feasibility) { "trace -> local test traffic -> stop" } else { "runner (pipeline streaming, player not launched) -> READY_FOR_TRACE -> start trace + START marker -> TRACE_STARTED -> player -> PREVIEW_DONE +${TailS} s or ${MaxSeconds} s hard deadline -> END marker -> stop trace -> runner shutdown (O2 reconnect untraced)" })
    runner = $(if ($Feasibility) { $null } else { "powershell $runnerArgs" })
    deadline_s = $MaxSeconds; retention = "raw retained locally (SHA-256) until validated extraction and the researcher's decision; never uploaded"
    post_processing = "decode the ETL (tracerpt CSV, raw FILETIME clock) and stream-extract the 127.0.0.1:8554 connections (tools/extract_o1_etw.py); no full XML export"
}
$plan | ConvertTo-Json -Depth 4
if (-not $Armed) { Write-Host "PLAN ONLY: nothing started."; exit 0 }

New-Item -ItemType Directory -Force $out | Out-Null
DisableQuickEdit
$host.UI.RawUI.WindowTitle = "O1 ETW $mode - please do not click inside this window"
Start-Transcript -Path (Join-Path $out "console_transcript.txt") -Append | Out-Null
$script:rp = $null
trap {
    Write-Host "ERROR: $_" -ForegroundColor Red
    try { StopTrace; Write-Host "Trace session stopped (or was not running)." } catch {}
    try { if ($script:rp -and -not $script:rp.HasExited) { New-Item -ItemType File -Force (Join-Path $gw "results\STAGE2_ABORT") | Out-Null; Write-Host "Runner asked to shut down (abort file)."; $null = $script:rp.WaitForExit($RunnerShutdownS * 1000); Remove-Item (Join-Path $gw "results\STAGE2_ABORT") -ErrorAction SilentlyContinue } } catch {}
    @{ error = "$_"; t = (Get-Date).ToString("o") } | ConvertTo-Json | Out-File -Encoding utf8 (Join-Path $out "capture_error.json")
    Heartbeat "error"
    Write-Host "=== STOPPED WITH AN ERROR. Files kept in $out. You can turn Wi-Fi back on. ===" -ForegroundColor Yellow
    try { Stop-Transcript | Out-Null } catch {}
    EndPause; exit 9
}
Heartbeat "started"
if (-not $Simulate) {
    if (-not $elevated) { Write-Host "REFUSED: needs an elevated Administrator PowerShell (or Performance Log Users)."; Stop-Transcript | Out-Null; EndPause; exit 3 }
    if (-not $isolated -and $WaitForIsolationMinutes -gt 0) {
        Write-Host ""; Write-Host "=== TURN WI-FI OFF NOW (system tray > Wi-Fi). Waiting up to $WaitForIsolationMinutes min; nothing starts until it is off. ===" -ForegroundColor Yellow
        $deadline = (Get-Date).AddMinutes($WaitForIsolationMinutes); $stableSince = $null
        while ((Get-Date) -lt $deadline) {
            $nl = NonLinkLocal; Heartbeat ("waiting_for_isolation; non_link_local=" + ($nl -join ' '))
            if ($nl.Count -eq 0) { if (-not $stableSince) { $stableSince = Get-Date; Write-Host "Isolated; confirming for 10 s..." }; if (((Get-Date) - $stableSince).TotalSeconds -ge 10) { break } }
            else { if ($stableSince) { Write-Host "Not isolated again ($($nl -join ', ')); waiting..." }; $stableSince = $null }
            Start-Sleep -Seconds 1
        }
        $nonLinkLocal = NonLinkLocal; $isolated = $nonLinkLocal.Count -eq 0 -and $stableSince -and ((Get-Date) - $stableSince).TotalSeconds -ge 10
    }
    if (-not $isolated) { Write-Host "REFUSED: not isolated ($($nonLinkLocal -join ', ')). Nothing started."; Stop-Transcript | Out-Null; EndPause; exit 4 }
    if (SessionExists) { Write-Host "REFUSED: an ETW session named $session already exists (logman stop $session -ets)."; Stop-Transcript | Out-Null; EndPause; exit 5 }
    if (-not $Feasibility -and -not (Get-ChildItem (Join-Path $gw "results") -Directory -Filter "o1_etw_feasibility_*" | Where-Object { Test-Path (Join-Path $_.FullName "feasibility_report.json") })) {
        Write-Host "REFUSED: no feasibility report."; Stop-Transcript | Out-Null; EndPause; exit 6 }
}
New-Item -ItemType Directory -Force $raw | Out-Null
$providers | Out-File -Encoding ascii (Join-Path $out "providers.txt")
$plan | ConvertTo-Json -Depth 4 | Out-File -Encoding utf8 (Join-Path $out "capture_plan.json")
$times = [ordered]@{}

if ($Feasibility) {
    $times.trace_start = (Get-Date).ToString("o"); StartTrace
    try { & $py -I (Join-Path $PSScriptRoot "o1_etw_feasibility_traffic.py") --out (Join-Path $out "markers.json") | Out-Null } finally { QuerySession; StopTrace; $times.trace_stop = (Get-Date).ToString("o") }
} else {
    Write-Host "Starting the runner (camera, MediaMTX, gateway; the player waits for the trace)..."
    $script:rp = Start-Process -FilePath powershell.exe -ArgumentList $runnerArgs -PassThru -WindowStyle Minimized
    $times.runner_started = (Get-Date).ToString("o"); Heartbeat "runner_started_waiting_ready"
    $t0 = Get-Date
    while (-not (Test-Path (Join-Path $hs "READY_FOR_TRACE"))) {
        if ($script:rp.HasExited) { $times.runner_exited_before_ready = (Get-Date).ToString("o"); break }
        if (((Get-Date) - $t0).TotalSeconds -gt $ReadyTimeoutS) { throw "runner not ready for the trace within $ReadyTimeoutS s" }
        Start-Sleep -Milliseconds 100
    }
    if ($times.runner_exited_before_ready) {
        Write-Host "The runner ended before the pipeline was ready; NO trace was started."
        $times.stop_reason = "runner_ended_before_ready"
    } else {
        $times.ready_seen = (Get-Date).ToString("o")
        StartTrace; $tTrace = Get-Date; $times.trace_start = $tTrace.ToString("o"); Heartbeat "tracing"
        Write-Host "Tracing started. Launching the player (60 s preview)..."
        Marker "start"
        (Get-Date).ToString("o") | Out-File -Encoding ascii (Join-Path $hs "TRACE_STARTED")
        if ($Simulate -and $SimFault -eq "wrapper_error") { throw "simulated wrapper error after the trace started" }
        $reason = $null
        while (-not $reason) {
            $el = ((Get-Date) - $tTrace).TotalSeconds
            if (Test-Path (Join-Path $hs "PREVIEW_DONE")) { $reason = "preview_done" }
            elseif ($script:rp.HasExited) { $reason = "runner_exited" }
            elseif ($el -ge ($MaxSeconds - 2)) { $reason = "deadline" }
            else { Start-Sleep -Milliseconds 200 }
        }
        if ($reason -eq "preview_done") { $tail = [Math]::Min($TailS, [Math]::Max(0, $MaxSeconds - 2 - ((Get-Date) - $tTrace).TotalSeconds)); Start-Sleep -Seconds $tail }
        Marker "end"; QuerySession; StopTrace
        $times.trace_stop = (Get-Date).ToString("o"); $times.stop_reason = $reason
        $times.trace_seconds = [math]::Round(((Get-Date) - $tTrace).TotalSeconds, 2); Heartbeat "tracing_stopped"
        Write-Host "Tracing stopped ($reason, $($times.trace_seconds) s). Waiting for the runner's orderly shutdown (includes the camera's post-run reconnect, about 75 s)..."
    }
    if (-not $script:rp.WaitForExit($RunnerShutdownS * 1000)) {
        New-Item -ItemType File -Force (Join-Path $gw "results\STAGE2_ABORT") | Out-Null; $times.runner_abort_file = $true
        $null = $script:rp.WaitForExit(240 * 1000); Remove-Item (Join-Path $gw "results\STAGE2_ABORT") -ErrorAction SilentlyContinue
    }
    $times.runner_exit_code = if ($script:rp.HasExited) { $script:rp.ExitCode } else { "still running" }
    $rd = Get-ChildItem (Join-Path $gw "results") -Directory -Filter "stage2_runner_*" | Where-Object { $_.CreationTime -ge [datetime]$times.runner_started } | Sort-Object Name | Select-Object -Last 1
    $times.runner_dir = if ($rd) { $rd.FullName } else { $null }
}
$times | ConvertTo-Json | Out-File -Encoding utf8 (Join-Path $out "capture_times.json")
$etl = Join-Path $raw "o1.etl"
$size = if (Test-Path $etl) { (Get-Item $etl).Length } else { 0 }
[ordered]@{ etl_bytes = $size; cap_bytes = [int64]$MaxMB * 1MB; cap_reached = ($size -ge ([int64]$MaxMB * 1MB * 0.99)); file_mode = $(if ($Feasibility) { "circular" } else { "sequential" })
            beginning_overwritten = $(if ($Feasibility) { "possible only if the cap was reached" } else { $false }); session_after_stop = $(if ($Simulate) { "simulated" } else { [int](SessionExists) }) } |
    ConvertTo-Json | Out-File -Encoding utf8 (Join-Path $out "trace_size_check.json")
if (Test-Path $etl) { Get-ChildItem $raw -File | ForEach-Object { "{0}  {1}  {2}" -f (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower(), $_.Length, $_.Name } | Out-File -Encoding utf8 (Join-Path $out "raw_sha256.txt") }
if ($Feasibility) {
    & tracerpt $etl -o (Join-Path $raw "o1_events.xml") -of XML -summary (Join-Path $out "o1_summary.txt") -y | Out-Null
    & $py -I (Join-Path $PSScriptRoot "analyse_o1_etw_feasibility.py") (Join-Path $raw "o1_events.xml") (Join-Path $out "markers.json") --summary (Join-Path $out "o1_summary.txt") --out (Join-Path $out "feasibility_report.json")
} elseif ((Test-Path $etl) -and -not $Simulate) {
    & tracerpt $etl -summary (Join-Path $out "o1_summary.txt") -report (Join-Path $out "o1_report.xml") -y | Out-Null   # counts / lost events only (no event dump)
}
"raw retained in raw\ (local only) until the researcher's decision" | Out-File -Encoding utf8 (Join-Path $out "retention.txt")
Heartbeat "finished"
Write-Host "Done: $out"
Write-Host ""; Write-Host "=== CAPTURE FINISHED AND TRACING STOPPED. YOU CAN TURN WI-FI BACK ON NOW. ===" -ForegroundColor Green
Stop-Transcript | Out-Null
EndPause
