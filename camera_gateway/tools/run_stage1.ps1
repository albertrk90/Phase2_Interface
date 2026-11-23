<#
Task 06 Stage 1 runner (approved 6 Nov 2026): Camera A on-device H.264, 30 s, files only.
No MediaMTX, no Unity, no other device. Runs independently of the Claude Code session
(start it through WMI), because the camera network is isolated and Claude Code is
offline while it runs.

  1. Pre-checks (read-only): no other camera process (camera_validation / camera_gateway
     Python), no MediaMTX, no Unity player; DepthAI crash-dump list.
  2. Keep-awake: SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) for this
     process only (no power setting changed; lapses when the process exits).
  3. WAITS (up to -WaitMinutes) until the host is ISOLATED: every non-loopback IPv4
     address is link-local 169.254.x.x (Wi-Fi off, camera Ethernet up), as Python's
     socket view sees it (the same view the gateway's connect_verified uses), stable for
     45 s (time for the PoE camera to boot into its bootloader). Nothing is contacted before that. Creating camera_gateway\results\STAGE1_DISARM
     at any time before the gateway starts cancels the run.
  4. Runs the gateway ONCE with the approved arguments:
       --expect 169.254.1.222=19443010B14C872F00 --baseline-user/--baseline-factory (Camera A)
       --live --sink file --seconds 30 --label stage1 --dump-raw
     (all safeguards are inside the gateway; it refuses on any identity, calibration,
     bootloader, IR or auto-calibration problem). Hard deadline 10 min. ONE retry, after
     30 s, only if the gateway's discovery pre-check found no camera ("nothing booted");
     any other refusal or failure is final.
  5. Post-checks: leftover gateway processes, crash-dump list again; then
     tools\analyse_stage1.py on the gateway's evidence folder (read-only).

Evidence: camera_gateway\results\stage1_runner_<stamp>\ (runner.log, runner_status.json,
gateway stdout/stderr) and the gateway's own camera_gateway\results\gw_<stamp>_A_stage1\.

  -DryRun  no waiting and no hardware: runs tools\dryrun_stage1_fake.py (fake device).
#>
param([switch]$DryRun, [int]$WaitMinutes = 45)
$ErrorActionPreference = "Stop"
$gw = Split-Path -Parent $PSScriptRoot
$root = Split-Path -Parent $gw
$py = Join-Path $gw ".venv\Scripts\python.exe"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$run = Join-Path $gw ("results\stage1_runner_" + $stamp + $(if ($DryRun) { "_dryrun" } else { "" }))
New-Item -ItemType Directory -Force $run | Out-Null
$disarm = Join-Path $gw "results\STAGE1_DISARM"
$crash = Join-Path $env:LOCALAPPDATA "depthai\cache\crashdumps"
$R = Join-Path $root "camera_validation\results"
$status = [ordered]@{ runner = "camera_gateway/tools/run_stage1.ps1"; dry_run = [bool]$DryRun; started = (Get-Date).ToString("o");
                      runner_pid = $PID; wait_minutes = $WaitMinutes; step = "start" }
function Log($m) { Add-Content -Path (Join-Path $run "runner.log") -Value ("{0} {1}" -f (Get-Date).ToString("HH:mm:ss.fff"), $m) }
function Save { $status.updated = (Get-Date).ToString("o"); $status | ConvertTo-Json -Depth 6 | Out-File -Encoding utf8 (Join-Path $run "runner_status.json") }
function Step($s) { $status.step = $s; Log "STEP $s"; Save }
function Dumps { if (Test-Path $crash) { @(Get-ChildItem $crash -Recurse -File | ForEach-Object { $_.FullName.Substring($crash.Length + 1) } | Sort-Object) } else { @() } }
function CamProcs { @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -match 'camera_gateway_a\.py|camera_validation\\\.venv|dryrun_stage1_fake\.py') -and $_.ProcessId -ne $PID } |
                     ForEach-Object { [ordered]@{ pid = $_.ProcessId; cmd = $_.CommandLine } }) }
function PyAddrs { @(& $py -I -c "import socket;print(chr(10).join(sorted({i[4][0] for i in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET)})))" 2>$null | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' }) }

Add-Type -Namespace Stage1 -Name Native -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
$ES_CONTINUOUS = [uint32]2147483648; $ES_SYSTEM_REQUIRED = [uint32]1
try {
    Step "pre_checks"
    $status.crash_dumps_before = @(Dumps)
    $other = @(CamProcs)
    $status.other_camera_processes = $other
    $status.mediamtx_running = [bool](Get-Process mediamtx -ErrorAction SilentlyContinue)
    $status.unity_player_running = [bool](Get-Process Phase2M1 -ErrorAction SilentlyContinue)
    if ($other.Count -gt 0 -or $status.mediamtx_running -or $status.unity_player_running) {
        $status.outcome = "refused_pre_checks"; Log "refused: another camera process, MediaMTX or Unity is running"; Save; return
    }
    $prev = [Stage1.Native]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)
    $status.keep_awake = [ordered]@{ held = ($prev -ne 0); flags = "0x80000001" }; Save

    if (-not $DryRun) {
        Step "wait_for_isolated_network"
        $deadline = (Get-Date).AddMinutes($WaitMinutes); $stableSince = $null; $last = ""
        while ($true) {
            if (Test-Path $disarm) { $status.outcome = "disarmed_before_start"; Log "disarm file found; nothing contacted"; Save; return }
            if ((Get-Date) -gt $deadline) { $status.outcome = "not_started_timeout"; Log "network never isolated within $WaitMinutes min; nothing contacted"; Save; return }
            $addrs = @(PyAddrs)
            $nonLoop = @($addrs | Where-Object { $_ -notlike "127.*" })
            $iso = ($nonLoop.Count -gt 0) -and (@($nonLoop | Where-Object { $_ -notlike "169.254.*" }).Count -eq 0)
            $now = ($addrs -join ","); if ($now -ne $last) { Log "host IPv4: $now (isolated: $iso)"; $last = $now }
            if ($iso) { if ($null -eq $stableSince) { $stableSince = Get-Date } elseif (((Get-Date) - $stableSince).TotalSeconds -ge 45) { break } }
            else { $stableSince = $null }
            Start-Sleep -Seconds 3
        }
        $status.isolated_addresses = $addrs; $status.isolated_at = (Get-Date).ToString("o")
        $gwArgs = @("-I", "`"$gw\camera_gateway_a.py`"", "--expect", "169.254.1.222=19443010B14C872F00",
                    "--baseline-user", "`"$R\calibration_user_19443010B14C872F00_20261103_182445.json`"",
                    "--baseline-factory", "`"$R\calibration_factory_19443010B14C872F00_20261103_182445.json`"",
                    "--live", "--sink", "file", "--seconds", "30", "--label", "stage1", "--dump-raw")
        $label = "stage1"
    } else {
        $gwArgs = @("-I", "`"$gw\tools\dryrun_stage1_fake.py`"", "--label", "stage1dry")
        $label = "stage1dry"
    }
    $status.gateway_command = "$py " + ($gwArgs -join " "); $status.attempts = @()
    $t0 = Get-Date
    foreach ($attempt in 1, 2) {
        if (Test-Path $disarm) { $status.outcome = "disarmed_before_start"; Save; return }
        Step "gateway_attempt_$attempt"
        $ta = Get-Date
        $p = Start-Process -FilePath $py -ArgumentList $gwArgs -WorkingDirectory $root -PassThru -WindowStyle Hidden `
             -RedirectStandardOutput (Join-Path $run "gateway_stdout_$attempt.txt") -RedirectStandardError (Join-Path $run "gateway_stderr_$attempt.txt")
        $null = $p.Handle
        $status.gateway_pid = $p.Id; Save
        if (-not $p.WaitForExit(600000)) {
            $status.deviation = "gateway exceeded the 10 min deadline and was stopped by the runner"; Log $status.deviation
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
        $status.gateway_exit_code = $p.ExitCode
        $status.gateway_seconds = [math]::Round(((Get-Date) - $ta).TotalSeconds, 1)
        $gd = Get-ChildItem (Join-Path $gw "results") -Directory -Filter "gw_*_A_$label" | Where-Object { $_.CreationTime -ge $ta.AddSeconds(-5) } |
              Sort-Object CreationTime | Select-Object -Last 1
        $errs = if ($gd -and (Test-Path (Join-Path $gd.FullName "report.json"))) { (Get-Content (Join-Path $gd.FullName "report.json") -Raw | ConvertFrom-Json).errors -join " | " } else { "" }
        $status.attempts += [ordered]@{ attempt = $attempt; exit_code = $p.ExitCode; dir = $(if ($gd) { $gd.FullName } else { $null }); errors = $errs }
        Save
        if ($attempt -eq 1 -and $p.ExitCode -ne 0 -and $errs -match "pre-check failed, nothing booted" -and -not $DryRun) {
            Log "attempt 1: camera not discoverable yet (nothing booted); one retry in 30 s"; Start-Sleep -Seconds 30; continue
        }
        break
    }
    Step "post_checks"
    Start-Sleep -Seconds 2
    $status.leftover_gateway_processes = @(CamProcs)
    $status.crash_dumps_after = @(Dumps)
    $status.new_crash_dumps = @($status.crash_dumps_after | Where-Object { $status.crash_dumps_before -notcontains $_ })
    $gwDir = Get-ChildItem (Join-Path $gw "results") -Directory -Filter "gw_*_A_$label" | Where-Object { $_.CreationTime -ge $t0.AddSeconds(-5) } |
             Sort-Object CreationTime | Select-Object -Last 1     # the final attempt
    $status.gateway_dir = if ($gwDir) { $gwDir.FullName } else { $null }
    $status.outcome = "gateway_finished"; Save
    if ($gwDir) {
        Step "analysis"
        & $py -I "$gw\tools\analyse_stage1.py" $gwDir.FullName --runner $run 2>&1 | Out-File -Encoding utf8 (Join-Path $run "analysis_stdout.txt")
        $status.analysis_exit_code = $LASTEXITCODE
    }
    Step "done"
} catch {
    $status.outcome = "runner_error"; $status.error = $_.ToString(); Log ("ERROR " + $_.ToString())
} finally {
    $null = [Stage1.Native]::SetThreadExecutionState($ES_CONTINUOUS)
    $status.finished = (Get-Date).ToString("o"); Save
}
