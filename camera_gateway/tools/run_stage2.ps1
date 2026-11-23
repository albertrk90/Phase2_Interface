<#
Task 06 Stage 2 runner: 60 s development preview, Camera A -> gateway (on-device H.264) -> localhost
MediaMTX -> Unity Phase2M1 (camera source). Camera A only; no robot, no COROL, no other device.
Runs independently of the Claude Code session (start it through WMI), because the laptop is on
the isolated camera network (Wi-Fi off) while it runs.

ORDER (each step bounded; any failure or abort goes to the same orderly shutdown):
  1  pre-checks: no camera / gateway / Unity / MediaMTX process; port 8554 free (TCP and UDP);
     MediaMTX config SHA-256 = the verified localhost-only config; mediamtx.exe SHA-256 = the binary
     of the checksum-verified v1.21.3 release; no stale streaming_poc\results\mediamtx.log; Unity
     player present; DepthAI crash-dump list. -PlanOnly stops here and prints the plan.
  2  keep-awake (per-process SetThreadExecutionState; no power setting changed)
  3  WAIT for the isolated network: every non-loopback IPv4 address link-local (Wi-Fi off), stable
     45 s, up to -WaitMinutes; never launches anything otherwise. Monitored for the whole run: any
     non-link-local address appearing aborts the run.
  4  MediaMTX (verified config) -> listener within 5 s -> its sockets must be exactly TCP 127.0.0.1:8554
  5  gateway (all Stage 1 safeguards; --sink rtsp; --seconds 120 as an upper bound; --stop-file)
     -> wait until BOTH eyes are published (gateway link_up events), <= 90 s. Unity is launched only
     after this, so the stream is already available when Unity connects (Unity needs about 8 s to start).
  6  Unity player (-m1Source camera -m1Seconds 60 -m1Quit), output in this runner folder;
     wait <= PreviewSeconds + 45 s. Camera and MediaMTX keep running until Unity has quit.
  7  gateway stop file -> the gateway ends the stream and runs its normal shutdown and post-run
     calibration verification (<= 180 s)
  8  MediaMTX stopped; its log moved into this folder
  9  final check (recorded BEFORE anything left over is stopped): no gateway, Unity or MediaMTX
     process, port 8554 closed, crash-dump list; then tools\analyse_stage2.py
ABORT: create camera_gateway\results\STAGE2_ABORT at any time -> orderly shutdown (Unity stopped,
gateway stop file, MediaMTX stopped, final check). Before step 4 nothing has been launched.

  -PlanOnly          pre-checks and the plan only; nothing launched
  -DryRun            OFFLINE: fake MediaMTX listener (127.0.0.1:8554, not MediaMTX), fake-device gateway
                     with a null output, fake Unity stand-in; no camera, no network wait
  -Fault             dry runs only: gateway_abort | unity_hang | unity_crash | late_player (with -ExtendedTest: pretends the
                     gateway's whole duration has already elapsed, so the launch-time check must refuse to start the player)
  -Keyint            Camera A H.264 keyframe interval: 20 (validated default) or 10 (proposed 6 Nov, under review)
  -NetworkScope      Isolated (validated default: Wi-Fi off, step 3 as above) | EthernetScoped (12 Nov 2026, approved
                     opt-in for the now-permitted concurrent Wi-Fi + Ethernet): step 3 waits for network_scope.py to pass
                     (stable 15 s), the run is aborted if it stops passing (checked at most every 5 s), the gateway runs
                     with --network-scope ethernet_scoped (no broadcast discovery), and a Wi-Fi probe (HTTPS every 5 s
                     to the university site, with the interface it used) is logged to wifi_probe.csv during the run.
  -Player            M1 (validated default: Phase2M1 camera preview) | S4Smoke (13 Nov 2026, approved): the S4.1 Site Window
                     (Builds\S4\SiteWindowSession.exe -s4LiveSmoke, protocol phase2_s41_live_smoke.json) with LIVE Camera A
                     (-s3AMode rtsp), Camera B the synthetic recording, the robot simulated. The gateway keeps its 120 s
                     limit: -PreviewSeconds is the player's hard stop and must be <= 85 (gateway start-up ~18 s + player
                     ~10 s + session + shutdown margin); the run is refused otherwise. Analysis: analyse_stage2.py --player s4.
                     S4Demo (13 Nov 2026, approved; needs -ExtendedTest): the existing full S4.1 INTERACTIVE demonstration
                     (phase2_s41_interactive_demo.json, unchanged) with LIVE Camera A, the facilitator console and a person
                     as the participant; ends when the window is closed (Alt+F4) or at the -PreviewSeconds deadline.
                     Commissioning (16 Nov 2026, for the Roseworthy commissioning): the commissioning VIEW
                     (Builds\Commissioning\CommissioningView.exe): LIVE Camera A only, free inspection (zoom/pan), truthful
                     video status, a remaining-time indicator and its own evidence (<run>\commissioning\). No trials, SAGAT,
                     confidence prompts, simulated robot actions or robot control. Without -ExtendedTest: 120 s gateway and
                     -PreviewSeconds <= 85, as S4Smoke. With -ExtendedTest: up to the same HARD 600 s. Ends at End view
                     (confirmed), the -PreviewSeconds time limit or the window closing. Analysis: analyse_stage2.py --player commissioning.
  -ExtendedTest      opt-in extended mode (S4Demo or Commissioning): the gateway may run for -GatewaySeconds up to a HARD 600 s
                     (camera_gateway_a.py --extended-test); the player deadline -PreviewSeconds must leave >= 75 s for
                     start-up and cleanup (PreviewSeconds <= GatewaySeconds - 75), and is re-checked against the gateway time
                     actually remaining before the player is launched. Without it: 120 s, exactly as before.
  -GatewaySeconds    gateway duration upper bound (default 120 = the validated value; > 120 only with -ExtendedTest).
#>
param([switch]$PlanOnly, [switch]$DryRun, [ValidateSet("none", "gateway_abort", "unity_hang", "unity_crash", "late_player")][string]$Fault = "none",
      [int]$WaitMinutes = 60, [int]$PreviewSeconds = 60, [ValidateSet(10, 20)][int]$Keyint = 20,
      [ValidateSet("Isolated", "EthernetScoped")][string]$NetworkScope = "Isolated",
      [ValidateSet("M1", "S4Smoke", "S4Demo", "Commissioning", "S4CorolViewing")][string]$Player = "M1",
      [switch]$ExtendedTest, [int]$GatewaySeconds = 120,
      [string]$TraceHandshakeDir = "", [int]$TraceHandshakeSeconds = 20)
# -TraceHandshakeDir (13 Nov 2026, opt-in, O1 diagnostic only): after the gateway is streaming and BEFORE the player is launched, write
#   <dir>\READY_FOR_TRACE and wait up to -TraceHandshakeSeconds (max 20) for <dir>\TRACE_STARTED (else orderly shutdown; player not
#   launched); write <dir>\PREVIEW_DONE as soon as the player has exited, BEFORE the gateway stop / post-run reconnect. Nothing else changes.
$S4 = ($Player -eq "S4Smoke")
# S4CorolViewing (18 Nov 2026, viewing rehearsal; needs -ExtendedTest): the one-placement COROL digital-twin rehearsal
#   (phase2_s41_corol_viewing.json) with slot A = SITE VIEW = LIVE Camera A filming a display of the running twin, slot B = WRIST VIEW =
#   the rendered virtual camera. Runs exactly like S4Demo (same gateway, limits and guards); the simulation-only twin, routine host and
#   wrist renderer must already be running (corol_sim\start_corol_sim.ps1 -Viewing). Physical Camera B is not connected.
$Viewing = ($Player -eq "S4CorolViewing")
$Demo = ($Player -eq "S4Demo") -or $Viewing
$CV = ($Player -eq "Commissioning")
$EXT_MAX = 600; $EXT_RESERVE = 75
$Scoped = ($NetworkScope -eq "EthernetScoped")
$ErrorActionPreference = "Stop"
$gw = Split-Path -Parent $PSScriptRoot
$root = Split-Path -Parent $gw
$poc = Join-Path $root "streaming_poc"
$unityProj = Join-Path $root "unity\Phase2Client"
$py = Join-Path $gw ".venv\Scripts\python.exe"
$mtxExe = Join-Path $poc "tools\mediamtx_v1.21.3\bin\mediamtx.exe"
$mtxCfg = Join-Path $poc "config\mediamtx_localhost.yml"
$mtxLog = Join-Path $poc "results\mediamtx.log"
$CFG_SHA = "782145b3fac5a219c6b0312a568b00607671b89f4d1bce6ab492f4d51024940a"   # verified localhost config (T3/T4 preflight)
$EXE_SHA = "13a0bfaa852d83ce976c94342a1af130941bd79fac2c1e95a2175879c92304c0"   # mediamtx.exe inside the checksum-verified v1.21.3 zip
$unityExe = if ($CV) { Join-Path $unityProj "Builds\Commissioning\CommissioningView.exe" } elseif ($Player -ne "M1") { Join-Path $unityProj "Builds\S4\SiteWindowSession.exe" } else { Join-Path $unityProj "Builds\M1\Phase2M1.exe" }
$smokeProtocol = Join-Path $unityProj "Assets\Phase2\Experiment\Protocols\phase2_s41_live_smoke.json"
$demoProtocol = Join-Path $unityProj $(if ($Viewing) { "Assets\Phase2\Experiment\Protocols\phase2_s41_corol_viewing.json" } else { "Assets\Phase2\Experiment\Protocols\phase2_s41_interactive_demo.json" })
$R = Join-Path $root "camera_validation\results"
$abortFile = Join-Path $gw "results\STAGE2_ABORT"
$crash = Join-Path $env:LOCALAPPDATA "depthai\cache\crashdumps"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$suffix = if ($PlanOnly) { "_planonly" } elseif ($DryRun) { "_dryrun_$Fault" } else { "" }
$run = Join-Path $gw ("results\stage2_runner_" + $stamp + $suffix)
New-Item -ItemType Directory -Force $run | Out-Null
$stopFile = Join-Path $run "GATEWAY_STOP"
$label = if ($DryRun) { "stage2dry" } else { "stage2" }
$status = [ordered]@{ runner = "camera_gateway/tools/run_stage2.ps1"; plan_only = [bool]$PlanOnly; dry_run = [bool]$DryRun; fault = $Fault;
                      started = (Get-Date).ToString("o"); runner_pid = $PID; preview_seconds = $PreviewSeconds; step = "start"; deviations = @();
                      network_scope = $NetworkScope; player = $Player; extended_test = [bool]$ExtendedTest; gateway_seconds = $GatewaySeconds }
function Log($m) { Add-Content -Path (Join-Path $run "runner.log") -Value ("{0} {1}" -f (Get-Date).ToString("HH:mm:ss.fff"), $m) }
function Save { $status.updated = (Get-Date).ToString("o"); $status | ConvertTo-Json -Depth 6 | Out-File -Encoding utf8 (Join-Path $run "runner_status.json") }
function Step($s) { $status.step = $s; Log "STEP $s"; Save }
function Deviation($m) { $status.deviations = @($status.deviations) + $m; Log "DEVIATION $m"; Save }
function Dumps { if (Test-Path $crash) { @(Get-ChildItem $crash -Recurse -File | ForEach-Object { $_.FullName.Substring($crash.Length + 1) } | Sort-Object) } else { @() } }
function FastPort {
    $ipg = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties()
    $t = @($ipg.GetActiveTcpListeners() | Where-Object { $_.Port -eq 8554 } | ForEach-Object { "$($_.Address):$($_.Port)" })
    $u = @($ipg.GetActiveUdpListeners() | Where-Object { $_.Port -eq 8554 } | ForEach-Object { "$($_.Address):$($_.Port)" })
    [pscustomobject]@{ tcp = $t; udp = $u; free = (($t.Count + $u.Count) -eq 0) }
}
function ByCmd($pattern) { @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -match $pattern -and $_.ProcessId -ne $PID } | ForEach-Object { [int]$_.ProcessId }) }
function GatewayProcs { ByCmd 'camera_gateway_a\.py|dryrun_stage[12]_fake\.py|camera_validation\\\.venv' }
function UnityProcs { @(@(Get-Process -Name Phase2M1, SiteWindowSession -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }) + @(ByCmd 'fake_unity_player\.py')) }
function MtxProcs { @(@(Get-Process -Name mediamtx -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }) + @(ByCmd 'fake_mediamtx\.py')) }
function PyAddrs { @(& $py -I -c "import socket;print(chr(10).join(sorted({i[4][0] for i in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET)})))" 2>$null | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' }) }
function Isolated($a) { $n = @($a | Where-Object { $_ -notlike "127.*" }); ($n.Count -gt 0) -and (@($n | Where-Object { $_ -notlike "169.254.*" }).Count -eq 0) }
$script:scopeLast = $null; $script:scopeAt = [datetime]::MinValue; $script:scopeChecks = 0
function ScopeCheck {
    $f = Join-Path $run "network_scope_last.json"
    & $py -I (Join-Path $gw "network_scope.py") --json $f 2>$null | Out-Null
    $code = $LASTEXITCODE; $script:scopeChecks++
    $script:scopeLast = if (Test-Path $f) { Get-Content $f -Raw | ConvertFrom-Json } else { $null }
    $script:scopeAt = Get-Date
    return ($code -eq 0)
}
function Guard {
    if (Test-Path $abortFile) { throw "ABORT: operator abort file" }
    if ($DryRun) { return }
    if ($Scoped) {
        if (((Get-Date) - $script:scopeAt).TotalSeconds -ge 5) { if (-not (ScopeCheck)) { throw "ABORT: ethernet-scoped network check failed: $($script:scopeLast.problems -join '; ')" } }
    } elseif (-not (Isolated (PyAddrs))) { throw "ABORT: network no longer isolated" }
}
$wifiJob = $null; $wifiStop = Join-Path $run "WIFI_PROBE_STOP"
function StartWifiProbe {
    $csv = Join-Path $run "wifi_probe.csv"
    $script:wifiJob = Start-Job -ArgumentList $csv, $wifiStop -ScriptBlock {
        param($csv, $stop)
        "t,url,status,ms,interface,source" | Out-File -Encoding utf8 $csv
        $u = "https://www.adelaide.edu.au/"
        $end = (Get-Date).AddMinutes(20)
        while (-not (Test-Path $stop) -and (Get-Date) -lt $end) {
            $t0 = Get-Date; $code = ""
            try { $code = (Invoke-WebRequest $u -UseBasicParsing -TimeoutSec 10 -MaximumRedirection 3).StatusCode } catch { $code = "ERR " + ($_.Exception.Message -replace ',', ';') }
            $ms = [int]((Get-Date) - $t0).TotalMilliseconds
            $ifc = ""; $src = ""
            try { $ip = (Resolve-DnsName www.adelaide.edu.au -Type A -ErrorAction Stop | Where-Object { $_.IPAddress } | Select-Object -First 1).IPAddress
                  $fr = @(Find-NetRoute -RemoteIPAddress $ip); $ifc = ($fr | Where-Object { $_.DestinationPrefix } | Select-Object -First 1).InterfaceAlias; $src = ($fr | Where-Object { $_.IPAddress } | Select-Object -First 1).IPAddress } catch { }
            "{0},{1},{2},{3},{4},{5}" -f $t0.ToString("HH:mm:ss.fff"), $u, $code, $ms, $ifc, $src | Out-File -Append -Encoding utf8 $csv
            Start-Sleep -Seconds 5
        }
    }
    $status.wifi_probe_started = (Get-Date).ToString("o"); Log "Wi-Fi probe started (HTTPS every 5 s -> wifi_probe.csv)"
}
function StopWifiProbe {
    if (-not $script:wifiJob) { return }
    Set-Content -Path $wifiStop -Value "stop" -Encoding ascii
    $null = Wait-Job $script:wifiJob -Timeout 30; Remove-Job $script:wifiJob -Force -ErrorAction SilentlyContinue; $script:wifiJob = $null
    $csv = Join-Path $run "wifi_probe.csv"
    if (Test-Path $csv) {
        $r = @(Import-Csv $csv)
        $ok = @($r | Where-Object { $_.status -eq "200" })
        $status.wifi_probe = [ordered]@{ probes = $r.Count; ok_200 = $ok.Count; failures = @($r | Where-Object { $_.status -ne "200" } | ForEach-Object { "$($_.t) $($_.status)" });
                                       max_ms = if ($ok.Count) { ($ok | ForEach-Object { [int]$_.ms } | Measure-Object -Maximum).Maximum } else { $null };
                                       interfaces = @($r | ForEach-Object { $_.interface } | Sort-Object -Unique) }
        Log "Wi-Fi probe: $($ok.Count)/$($r.Count) HTTPS 200"
    }
}
function Sockets($procId) {
    $s = @()
    $s += @(Get-NetTCPConnection -OwningProcess $procId -State Listen -ErrorAction SilentlyContinue | ForEach-Object { [ordered]@{ proto = "TCP"; address = $_.LocalAddress; port = [int]$_.LocalPort } })
    $s += @(Get-NetUDPEndpoint -OwningProcess $procId -ErrorAction SilentlyContinue | ForEach-Object { [ordered]@{ proto = "UDP"; address = $_.LocalAddress; port = [int]$_.LocalPort } })
    $s
}
function KillAll($ids, $what) { foreach ($i in $ids) { Stop-Process -Id $i -Force -ErrorAction SilentlyContinue }; if (@($ids).Count) { Log "stopped $what $($ids -join ',')" } }

Add-Type -Namespace Stage2 -Name Native -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
$ES_CONTINUOUS = [uint32]2147483648; $ES_SYSTEM_REQUIRED = [uint32]1
$mtx = $null; $gwp = $null; $unity = $null; $gwDir = $null; $shutdownDone = $false

function Shutdown($why) {
    if ($script:shutdownDone) { return }
    $script:shutdownDone = $true
    $status.shutdown_reason = $why; Step "shutdown"
    StopWifiProbe
    if ($script:unity -and -not $script:unity.HasExited) { Deviation "Unity still running at shutdown ($why): stopped"; KillAll (UnityProcs) "unity" }
    if ($script:gwp) {
        if (-not $script:gwp.HasExited) {
            Set-Content -Path $stopFile -Value $why -Encoding ascii
            Log "gateway stop file written"
            if (-not $script:gwp.WaitForExit(180000)) { Deviation "gateway did not exit within 180 s of the stop file: stopped (camera session forcibly ended)"; KillAll (GatewayProcs) "gateway" }
        }
        $status.gateway_exit_code = $script:gwp.ExitCode
    }
    if ($script:mtx) {
        if (-not $script:mtx.HasExited) { Stop-Process -Id $script:mtx.Id -Force; $null = $script:mtx.WaitForExit(5000) }
        $status.mediamtx_stopped = $script:mtx.HasExited
        if (-not $DryRun -and (Test-Path $mtxLog)) { Move-Item $mtxLog (Join-Path $run "mediamtx.log") -Force }
    }
    Step "final_check"
    Start-Sleep -Seconds 1
    $fp = FastPort
    $fin = [ordered]@{ checked_at = (Get-Date).ToString("o"); gateway_processes = @(GatewayProcs); unity_processes = @(UnityProcs);
                       mediamtx_processes = @(MtxProcs); port_8554_free = $fp.free; port_8554_tcp = @($fp.tcp); port_8554_udp = @($fp.udp) }
    $status.final_check = $fin
    $status.crash_dumps_after = @(Dumps)
    $status.new_crash_dumps = @($status.crash_dumps_after | Where-Object { $status.crash_dumps_before -notcontains $_ })
    Save
    $left = @($fin.gateway_processes) + @($fin.unity_processes) + @($fin.mediamtx_processes)
    if ($left.Count) { Deviation "processes left after shutdown (recorded above, now stopped): $($left -join ',')"; KillAll $left "leftovers" }
}

try {
    Step "pre_checks"
    $pre = [ordered]@{}
    $pre.gateway_processes = @(GatewayProcs); $pre.unity_processes = @(UnityProcs); $pre.mediamtx_processes = @(MtxProcs)
    $fp = FastPort; $pre.port_8554_free = $fp.free
    $pre.mediamtx_config_sha256 = (Get-FileHash $mtxCfg).Hash.ToLower(); $pre.mediamtx_config_verified = ($pre.mediamtx_config_sha256 -eq $CFG_SHA)
    $pre.mediamtx_exe_sha256 = (Get-FileHash $mtxExe).Hash.ToLower(); $pre.mediamtx_exe_verified = ($pre.mediamtx_exe_sha256 -eq $EXE_SHA)
    $pre.stale_mediamtx_log = (Test-Path $mtxLog)
    $pre.unity_player = (Test-Path $unityExe)
    $pre.unity_assembly_time = if (Test-Path (Join-Path $unityProj "Builds\M1\Phase2M1_Data\Managed\Phase2.Video.Unity.dll")) { (Get-Item (Join-Path $unityProj "Builds\M1\Phase2M1_Data\Managed\Phase2.Video.Unity.dll")).LastWriteTime.ToString("o") } else { $null }
    if ($Demo) {
        $pre.s4_player_time = if (Test-Path $unityExe) { (Get-Item $unityExe).LastWriteTime.ToString("o") } else { $null }
        $pre.demo_protocol = (Test-Path $demoProtocol)
        $pre.demo_protocol_sha256 = if ($pre.demo_protocol) { (Get-FileHash $demoProtocol).Hash.ToLower() } else { $null }
    }
    $pre.duration = [ordered]@{ gateway_seconds = $GatewaySeconds; player_deadline_s = $PreviewSeconds; extended_test = [bool]$ExtendedTest;
                                limit_s = $(if ($ExtendedTest) { $EXT_MAX } else { 120 }); reserve_s = $(if ($ExtendedTest) { $EXT_RESERVE } else { $null }) }
    if ($S4) {
        $pre.s4_player_time = if (Test-Path $unityExe) { (Get-Item $unityExe).LastWriteTime.ToString("o") } else { $null }
        $pre.smoke_protocol = (Test-Path $smokeProtocol)
        $pre.smoke_protocol_sha256 = if ($pre.smoke_protocol) { (Get-FileHash $smokeProtocol).Hash.ToLower() } else { $null }
        $pre.preview_within_gateway_limit = ($PreviewSeconds -le 85)
    }
    if ($CV) {
        $pre.cv_player_time = if (Test-Path $unityExe) { (Get-Item $unityExe).LastWriteTime.ToString("o") } else { $null }
        $pre.preview_within_gateway_limit = if ($ExtendedTest) { $null } else { ($PreviewSeconds -le 85) }
    }
    $pre.abort_file_present = (Test-Path $abortFile)
    $status.pre_checks = $pre
    $status.crash_dumps_before = @(Dumps)
    $status.mediamtx_config_verified = $pre.mediamtx_config_verified; $status.port_8554_free_before = $pre.port_8554_free
    $problems = @()
    if ($pre.gateway_processes.Count + $pre.unity_processes.Count + $pre.mediamtx_processes.Count) { $problems += "a camera, gateway, Unity or MediaMTX process is already running" }
    if (-not $pre.port_8554_free) { $problems += "port 8554 is not free" }
    if (-not $pre.mediamtx_config_verified) { $problems += "MediaMTX config differs from the verified localhost-only config" }
    if (-not $pre.mediamtx_exe_verified) { $problems += "mediamtx.exe differs from the verified release binary" }
    if ($pre.stale_mediamtx_log) { $problems += "a previous streaming_poc\results\mediamtx.log exists (would be mixed into this evidence)" }
    if (-not $pre.unity_player) { $problems += "Unity player missing" }
    if ($pre.abort_file_present) { $problems += "abort file present" }
    if ($S4 -and -not $pre.smoke_protocol) { $problems += "live smoke protocol missing" }
    if (($S4 -or ($CV -and -not $ExtendedTest)) -and -not $pre.preview_within_gateway_limit) { $problems += "-PreviewSeconds $PreviewSeconds would not fit inside the gateway's 120 s limit (max 85); the limit is not raised" }
    if ($ExtendedTest -and -not ($Demo -or $CV)) { $problems += "-ExtendedTest applies only to -Player S4Demo or Commissioning (the M1 preview and the S4Smoke test keep their 120 s behaviour)" }
    if ($Demo -and -not $ExtendedTest) { $problems += "-Player S4Demo needs -ExtendedTest (the full demonstration does not fit 120 s)" }
    if (-not $ExtendedTest -and $GatewaySeconds -ne 120) { $problems += "-GatewaySeconds $GatewaySeconds needs -ExtendedTest (default limit 120 s)" }
    if ($ExtendedTest -and ($GatewaySeconds -lt 120 -or $GatewaySeconds -gt $EXT_MAX)) { $problems += "-GatewaySeconds $GatewaySeconds outside 120-$EXT_MAX s (extended-test hard maximum $EXT_MAX s)" }
    if ($ExtendedTest -and $PreviewSeconds -gt ($GatewaySeconds - $EXT_RESERVE)) { $problems += "-PreviewSeconds $PreviewSeconds must leave $EXT_RESERVE s of the gateway's $GatewaySeconds s for start-up and cleanup (max $($GatewaySeconds - $EXT_RESERVE))" }
    if ($Demo -and -not $pre.demo_protocol) { $problems += "interactive demonstration protocol missing" }
    if ($Viewing) {   # the simulation-only twin, routine host and wrist renderer (all on 127.0.0.1)
        $pre.viewing = [ordered]@{}
        try { $g = Invoke-RestMethod http://127.0.0.1:8080/api/phase2/sim_guard -TimeoutSec 3; $pre.viewing.twin_sim_only = [bool]$g.sim_only } catch { $pre.viewing.twin_sim_only = $false }
        try { $h = Invoke-RestMethod http://127.0.0.1:8095/api/status -TimeoutSec 3; $pre.viewing.host_simulation_only = [bool]$h.simulation_only } catch { $pre.viewing.host_simulation_only = $false }
        $w = $null; try { $v = Invoke-RestMethod http://127.0.0.1:8080/api/phase2/vcam -TimeoutSec 3; $w = $v.cameras.wrist; $pre.viewing.wrist_age_ms = $w.age_since_capture_ms } catch { }
        $pre.viewing.wrist_streaming = [bool]($w -and $w.age_since_capture_ms -lt 2000)
        if (-not $pre.viewing.twin_sim_only) { $problems += "the simulation-only COROL twin is not running on 127.0.0.1:8080 (corol_sim\start_corol_sim.ps1 -Viewing)" }
        if (-not $pre.viewing.host_simulation_only) { $problems += "the simulation-only routine host is not running on 127.0.0.1:8095" }
        if (-not $pre.viewing.wrist_streaming) { $problems += "the wrist virtual camera is not streaming (corol_sim\vcam_render.py --cams wrist)" }
    }
    $status.pre_check_problems = $problems
    $R_ = $R
    $gwArgs = if ($DryRun) { @("-I", "`"$gw\tools\dryrun_stage2_fake.py`"", "--label", $label, "--stop-file", "`"$stopFile`"", "--seconds", "$GatewaySeconds") + $(if ($ExtendedTest) { @("--extended-test") } else { @() }) + $(if ($Fault -eq "gateway_abort") { @("--fault", "bootloader") } else { @() }) }
              else { @("-I", "`"$gw\camera_gateway_a.py`"", "--expect", "169.254.1.222=19443010B14C872F00",
                       "--baseline-user", "`"$R_\calibration_user_19443010B14C872F00_20261103_182445.json`"",
                       "--baseline-factory", "`"$R_\calibration_factory_19443010B14C872F00_20261103_182445.json`"",
                       "--live", "--sink", "rtsp", "--server", "rtsp://127.0.0.1:8554", "--seconds", "$GatewaySeconds", "--keyint", "$Keyint", "--label", $label,
                       "--stop-file", "`"$stopFile`"") + $(if ($Scoped) { @("--network-scope", "ethernet_scoped") } else { @() }) + $(if ($ExtendedTest) { @("--extended-test") } else { @() }) }
    $m1Args = @("-m1Mode", "rtsp", "-m1Server", "rtsp://127.0.0.1:8554", "-m1Source", "camera", "-m1Seconds", "$PreviewSeconds",
                "-m1Label", "camA_preview", "-m1Quit", "-m1Out", "`"$run`"", "-m1SaveEvery", "200", "-logFile", "`"$run\unity_player.log`"",
                "-screen-fullscreen", "0", "-screen-width", "1280", "-screen-height", "800")
    $unityArgs = if ($CV) {
        @("-cvMode", "rtsp", "-cvServer", "rtsp://127.0.0.1:8554", "-cvSeconds", "$PreviewSeconds", "-cvLaunchSeconds", "$GatewaySeconds",
          "-cvQuit", "-cvOut", "`"$run\commissioning`"", "-m1Out", "`"$run`"", "-logFile", "`"$run\unity_player.log`"",
          "-screen-fullscreen", "0", "-popupwindow", "-screen-width", "1920", "-screen-height", "1080")
    } elseif ($Demo) {
        @("-s4", "-s4Protocol", "`"$demoProtocol`"", "-s4Root", "`"$run\s4_sessions`"", "-s3AMode", "rtsp", "-s3AServer", "rtsp://127.0.0.1:8554",
          "-s3Seconds", "$PreviewSeconds", "-s3Quit", "-m1Out", "`"$run`"", "-logFile", "`"$run\unity_player.log`"",
          "-screen-fullscreen", "0", "-popupwindow", "-screen-width", "1920", "-screen-height", "1080") +
        $(if ($Viewing) { @("-s4Corol", "-s4Viewing", "-s3ASiteDisplay", "-s3BMode", "virtual", "-s3BVcam", "wrist", "-s3VcamHost", "http://127.0.0.1:8080") } else { @() })
    } elseif ($S4) {
        @("-s4", "-s4LiveSmoke", "-s4Protocol", "`"$smokeProtocol`"", "-s4Root", "`"$run\s4_sessions`"", "-s3AMode", "rtsp", "-s3AServer", "rtsp://127.0.0.1:8554",
          "-s3Seconds", "$PreviewSeconds", "-s3Shots", "-s3Quit", "-m1Out", "`"$run`"", "-logFile", "`"$run\unity_player.log`"",
          "-screen-fullscreen", "0", "-popupwindow", "-screen-width", "1920", "-screen-height", "1080")
    } else {
        @("-m1Mode", "rtsp", "-m1Server", "rtsp://127.0.0.1:8554", "-m1Source", "camera", "-m1Seconds", "$PreviewSeconds",
          "-m1Label", "camA_preview", "-m1Quit", "-m1Out", "`"$run`"", "-m1SaveEvery", "200", "-logFile", "`"$run\unity_player.log`"",
          "-screen-fullscreen", "0", "-screen-width", "1280", "-screen-height", "800")
    }
    $status.plan = [ordered]@{
        mediamtx = if ($DryRun) { "$py -I tools\fake_mediamtx.py 8554   (FAKE listener)" } else { "$mtxExe `"$mtxCfg`"   (cwd $poc)" };
        gateway = "$py " + ($gwArgs -join " ");
        unity = $(if ($DryRun) { "$py -I tools\fake_unity_player.py " + ($unityArgs -join " ") + " --fake-gateway-dir <gw dir>" } else { "$unityExe " + ($unityArgs -join " ") });
        timeouts_s = [ordered]@{ isolation_wait = $WaitMinutes * 60; mediamtx_listen = 5; gateway_streaming = 90; unity = $PreviewSeconds + 45; gateway_stop = 180; mediamtx_stop = 5 };
        abort_file = $abortFile; output = $run }
    Save
    if ($problems.Count) { $status.outcome = "refused_pre_checks"; Log ("refused: " + ($problems -join "; ")); return }
    if ($PlanOnly) { $status.outcome = "plan_only"; Log "plan only: nothing launched"; $status.plan | ConvertTo-Json -Depth 4; return }

    $prev = [Stage2.Native]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)
    $status.keep_awake = [ordered]@{ held = ($prev -ne 0); flags = "0x80000001" }
    if (-not $DryRun -and $Scoped) {
        Step "wait_for_scoped_network"
        $deadline = (Get-Date).AddMinutes($WaitMinutes); $stableSince = $null; $lastOk = $null
        while ($true) {
            if (Test-Path $abortFile) { $status.outcome = "aborted_before_launch"; Log "abort file: nothing launched or contacted"; return }
            if ((Get-Date) -gt $deadline) { $status.outcome = "not_started_timeout"; Log "ethernet-scoped network never passed; nothing launched or contacted"; return }
            $okNow = ScopeCheck
            if ($okNow -ne $lastOk) { Log "ethernet-scoped check: $okNow $(if (-not $okNow) { $script:scopeLast.problems -join '; ' })"; $lastOk = $okNow }
            if ($okNow) { if ($null -eq $stableSince) { $stableSince = Get-Date } elseif (((Get-Date) - $stableSince).TotalSeconds -ge 15) { break } } else { $stableSince = $null }
            Start-Sleep -Seconds 3
        }
        $status.network_scope_pre_check = $script:scopeLast
        StartWifiProbe
    } elseif (-not $DryRun) {
        Step "wait_for_isolated_network"
        $deadline = (Get-Date).AddMinutes($WaitMinutes); $stableSince = $null; $last = ""
        while ($true) {
            if (Test-Path $abortFile) { $status.outcome = "aborted_before_launch"; Log "abort file: nothing launched or contacted"; return }
            if ((Get-Date) -gt $deadline) { $status.outcome = "not_started_timeout"; Log "network never isolated; nothing launched or contacted"; return }
            $a = @(PyAddrs); $iso = Isolated $a
            $now = ($a -join ","); if ($now -ne $last) { Log "host IPv4: $now (isolated: $iso)"; $last = $now }
            if ($iso) { if ($null -eq $stableSince) { $stableSince = Get-Date } elseif (((Get-Date) - $stableSince).TotalSeconds -ge 45) { break } } else { $stableSince = $null }
            Start-Sleep -Seconds 3
        }
        $status.isolated_addresses = @($a)
    } else { $status.network = "SIMULATED (dry run: no isolation required, nothing contacted)" }

    Step "start_mediamtx"
    if ($DryRun) {
        $mtx = Start-Process -FilePath $py -ArgumentList @("-I", "`"$gw\tools\fake_mediamtx.py`"", "8554") -PassThru -WindowStyle Hidden
    } else {
        $mtx = Start-Process -FilePath $mtxExe -ArgumentList "`"$mtxCfg`"" -WorkingDirectory $poc -PassThru -WindowStyle Hidden `
               -RedirectStandardOutput (Join-Path $run "mediamtx_stdout.txt") -RedirectStandardError (Join-Path $run "mediamtx_stderr.txt")
    }
    $null = $mtx.Handle
    $status.mediamtx_started = $true; $status.mediamtx_pid = $mtx.Id
    $t = Get-Date
    do { Start-Sleep -Milliseconds 50; $fp = FastPort } until ((-not $fp.free) -or $mtx.HasExited -or ((Get-Date) - $t).TotalSeconds -gt 5)
    if ($mtx.HasExited -or $fp.free) { throw "MediaMTX did not start listening within 5 s (exited=$($mtx.HasExited))" }
    $sockPid = $mtx.Id
    if ($DryRun) { $child = @(ByCmd 'fake_mediamtx\.py' | Where-Object { $_ -ne $mtx.Id }); if ($child.Count) { $sockPid = $child[0] } }
    Start-Sleep -Milliseconds 500
    $socks = @(Sockets $sockPid)
    if ($DryRun -and $socks.Count -eq 0) { $socks = @(Sockets $mtx.Id) }
    $status.mediamtx_sockets = $socks; Save
    $exact = ($socks.Count -eq 1) -and ($socks[0].proto -eq "TCP") -and ($socks[0].address -eq "127.0.0.1") -and ($socks[0].port -eq 8554)
    if (-not $exact) { throw "MediaMTX sockets are not exactly TCP 127.0.0.1:8554: $($socks | ConvertTo-Json -Compress)" }
    Log "MediaMTX listening: TCP 127.0.0.1:8554 only"

    Step "start_gateway"
    Guard
    $tg = Get-Date
    $gwp = Start-Process -FilePath $py -ArgumentList $gwArgs -WorkingDirectory $root -PassThru -WindowStyle Hidden `
           -RedirectStandardOutput (Join-Path $run "gateway_stdout.txt") -RedirectStandardError (Join-Path $run "gateway_stderr.txt")
    $null = $gwp.Handle
    $status.gateway_pid = $gwp.Id; Save
    Step "wait_gateway_streaming"
    $streaming = $false
    while (((Get-Date) - $tg).TotalSeconds -lt 90) {
        Guard
        if (-not $gwDir) { $gwDir = Get-ChildItem (Join-Path $gw "results") -Directory -Filter "gw_*_A_$label" | Where-Object { $_.CreationTime -ge $tg.AddSeconds(-2) } | Sort-Object CreationTime | Select-Object -Last 1 }
        if ($gwDir) {
            $status.gateway_dir = $gwDir.FullName
            $ev = Join-Path $gwDir.FullName "events.jsonl"
            if (Test-Path $ev) {
                $ups = @(Get-Content $ev | Where-Object { $_ -match '"type":\s*"link_up"' } | ForEach-Object { ($_ | ConvertFrom-Json).payload.eye } | Sort-Object -Unique)
                if (($ups -contains "left") -and ($ups -contains "right")) { $streaming = $true; break }
            }
        }
        if ($gwp.HasExited) { break }
        Start-Sleep -Milliseconds 500
    }
    $status.gateway_streaming = $streaming; $status.gateway_streaming_after_s = [math]::Round(((Get-Date) - $tg).TotalSeconds, 1); Save
    if (-not $streaming) { throw $(if ($gwp.HasExited) { "gateway exited before streaming (exit $($gwp.ExitCode)); Unity not launched" } else { "gateway not streaming within 90 s; Unity not launched" }) }
    Log "gateway streaming on both eyes after $($status.gateway_streaming_after_s) s"

    if ($TraceHandshakeDir) {
        $TraceHandshakeSeconds = [Math]::Max(1, [Math]::Min($TraceHandshakeSeconds, 20))
        Step "trace_handshake"
        New-Item -ItemType Directory -Force $TraceHandshakeDir | Out-Null
        (Get-Date).ToString("o") | Out-File -Encoding ascii (Join-Path $TraceHandshakeDir "READY_FOR_TRACE")
        $th = Get-Date
        while (-not (Test-Path (Join-Path $TraceHandshakeDir "TRACE_STARTED"))) {
            Guard
            if ($gwp.HasExited) { throw "gateway exited during the trace handshake (exit $($gwp.ExitCode)); Unity not launched" }
            if (((Get-Date) - $th).TotalSeconds -gt $TraceHandshakeSeconds) { throw "trace not started within $TraceHandshakeSeconds s of READY_FOR_TRACE; Unity not launched" }
            Start-Sleep -Milliseconds 100
        }
        $status.trace_handshake = [ordered]@{ dir = $TraceHandshakeDir; wait_s = [math]::Round(((Get-Date) - $th).TotalSeconds, 2) }; Save
        Log "trace started (handshake after $($status.trace_handshake.wait_s) s); launching the player"
    }
    Step "start_unity"
    Guard
    if ($ExtendedTest) {
        $left = $GatewaySeconds - ((Get-Date) - $tg).TotalSeconds - $(if ($DryRun -and $Fault -eq "late_player") { $GatewaySeconds } else { 0 })

        $status.gateway_seconds_left_at_player_launch = [math]::Round($left, 1)
        if ($PreviewSeconds + 45 -gt $left) { throw "insufficient gateway time left ($([math]::Round($left, 1)) s) for the player deadline $PreviewSeconds s + 45 s; player not launched" }
    }
    $status.unity_launched = (Get-Date).ToString("o")
    if ($DryRun) {
        $fu = @("-I", "`"$gw\tools\fake_unity_player.py`"") + $m1Args + @("--fake-gateway-dir", "`"$($gwDir.FullName)`"") +   # the fake is an M1 stand-in (orchestration only)

              $(if ($Fault -eq "unity_hang") { @("--fake-fault", "hang") } elseif ($Fault -eq "unity_crash") { @("--fake-fault", "crash") } else { @() })
        $unity = Start-Process -FilePath $py -ArgumentList $fu -PassThru -WindowStyle Hidden
    } else {
        $unity = Start-Process -FilePath $unityExe -ArgumentList $unityArgs -WorkingDirectory $unityProj -PassThru
    }
    $null = $unity.Handle
    $status.unity_pid = $unity.Id; Save
    Step "wait_unity_preview"
    $tu = Get-Date; $gwEndedEarly = $false
    while (-not $unity.HasExited) {
        Guard
        if (((Get-Date) - $tu).TotalSeconds -gt ($PreviewSeconds + 45)) { Deviation "Unity did not quit within $($PreviewSeconds + 45) s: stopped"; KillAll (UnityProcs) "unity"; break }
        if (-not $gwEndedEarly -and $gwp.HasExited) { $gwEndedEarly = $true; Deviation "gateway ended during the preview (exit $($gwp.ExitCode))" }
        if ($mtx.HasExited) { Deviation "MediaMTX exited during the preview"; break }
        Start-Sleep -Milliseconds 500
    }
    $null = $unity.WaitForExit(5000)
    $status.unity_exit_code = if ($unity.HasExited) { $unity.ExitCode } else { "running" }
    $status.unity_seconds = [math]::Round(((Get-Date) - $tu).TotalSeconds, 1)
    Log "Unity exited (code $($status.unity_exit_code)) after $($status.unity_seconds) s"
    if ($TraceHandshakeDir) { (Get-Date).ToString("o") | Out-File -Encoding ascii (Join-Path $TraceHandshakeDir "PREVIEW_DONE") }   # before gateway stop / post-run reconnect
    Shutdown "preview_complete"
    $status.outcome = if ((@($status.deviations).Count -eq 0) -and ($status.unity_exit_code -eq 0)) { "completed" } else { "completed_with_deviations" }
} catch {
    $msg = $_.ToString()
    $status.outcome = if ($msg -like "ABORT:*") { "aborted" } else { "failed" }
    $status.error = $msg; Log "ERROR $msg"; Save
    try { Shutdown $status.outcome } catch { $status.shutdown_error = $_.ToString(); Log "SHUTDOWN ERROR $($_.ToString())" }
} finally {
    if (-not $PlanOnly -and -not $script:shutdownDone -and ($mtx -or $gwp -or $unity)) { try { Shutdown "finally" } catch { $status.shutdown_error = $_.ToString() } }
    $null = [Stage2.Native]::SetThreadExecutionState($ES_CONTINUOUS)
    if ($status.final_check) {
        Step "analysis"
        if ($Demo) {
            $s4out = Get-ChildItem (Join-Path $unityProj "test_results") -Directory -Filter "ai2_s4_*_win64player" | Where-Object { $status.unity_launched -and $_.CreationTime -ge ([datetime]$status.unity_launched).AddSeconds(-5) } | Sort-Object Name | Select-Object -Last 1
            $sess = Get-ChildItem (Join-Path $run "s4_sessions") -Directory -Filter "S4-*" -ErrorAction SilentlyContinue | Select-Object -Last 1
            $status.s4_ui_out = if ($s4out) { $s4out.FullName } else { $null }; $status.s4_session_dir = if ($sess) { $sess.FullName } else { $null }
            $status.receiver_dirs = @(Get-ChildItem $run -Directory -Filter "unity_rx_*" | ForEach-Object { $_.Name }); Save
            # one analysis per LIVE Camera A receiver (a receiver per trial reset), then the walkthrough summary
            $codes = @()
            if ($gwDir) {
                foreach ($ua in @(Get-ChildItem $run -Directory -Filter "unity_rx_*_A_*" | Sort-Object Name)) {
                    $aa = @("-I", "$gw\tools\analyse_stage2.py", "--gw", $gwDir.FullName, "--runner", $run, "--unity", $ua.FullName, "--player", "s4demo",
                            "--out", "stage2_analysis_$($ua.Name).json") + $(if ($status.s4_ui_out) { @("--s4-out", $status.s4_ui_out) } else { @() }) +
                          $(if ($status.s4_session_dir) { @("--s4-session", $status.s4_session_dir) } else { @() })
                    & $py @aa 2>&1 | Out-File -Append -Encoding utf8 (Join-Path $run "analysis_stdout.txt"); $codes += $LASTEXITCODE
                }
            } else { Log "no gateway folder: analysis skipped" }
            $status.analysis_exit_code = if ($codes.Count) { ($codes | Measure-Object -Maximum).Maximum } else { $null }
        } else {
        if ($S4) {
            # the live Camera A receiver of the measured trial (one per trial reset; the smoke protocol has one trial)

            $u = Get-ChildItem $run -Directory -Filter "unity_rx_*_A_*" | Sort-Object Name | Select-Object -Last 1
            $s4out = Get-ChildItem (Join-Path $unityProj "test_results") -Directory -Filter "ai2_s4_*_win64player" | Where-Object { $status.unity_launched -and $_.CreationTime -ge ([datetime]$status.unity_launched).AddSeconds(-5) } | Sort-Object Name | Select-Object -Last 1
            $sess = Get-ChildItem (Join-Path $run "s4_sessions") -Directory -Filter "S4-*" -ErrorAction SilentlyContinue | Select-Object -Last 1
            $status.s4_ui_out = if ($s4out) { $s4out.FullName } else { $null }; $status.s4_session_dir = if ($sess) { $sess.FullName } else { $null }
            $status.receiver_dirs = @(Get-ChildItem $run -Directory -Filter "unity_rx_*" | ForEach-Object { $_.Name }); Save
        } elseif ($CV) {
            # the view's one live Camera A receiver, and the view's own evidence folder
            $u = Get-ChildItem $run -Directory -Filter "unity_rx_*_A_commissioning" | Sort-Object Name | Select-Object -Last 1
            $cvDir = Get-ChildItem (Join-Path $run "commissioning") -Directory -Filter "commissioning_*" -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1
            $status.cv_out = if ($cvDir) { $cvDir.FullName } else { $null }
            $status.receiver_dirs = @(Get-ChildItem $run -Directory -Filter "unity_rx_*" | ForEach-Object { $_.Name }); Save
        } else {
            $u = Get-ChildItem $run -Directory -Filter "unity_rx_*" | Select-Object -Last 1
        }
        $a = @("-I", "$gw\tools\analyse_stage2.py", "--gw", $(if ($gwDir) { $gwDir.FullName } else { "NONE" }), "--runner", $run) + $(if ($u) { @("--unity", $u.FullName) } else { @() }) +
             $(if ($CV) { @("--player", "commissioning") + $(if ($status.cv_out) { @("--cv-out", $status.cv_out) } else { @() }) } else { @() }) +
             $(if ($S4) { @("--player", "s4") + $(if ($status.s4_ui_out) { @("--s4-out", $status.s4_ui_out) } else { @() }) + $(if ($status.s4_session_dir) { @("--s4-session", $status.s4_session_dir) } else { @() }) } else { @() })

        if ($gwDir) { & $py @a 2>&1 | Out-File -Encoding utf8 (Join-Path $run "analysis_stdout.txt"); $status.analysis_exit_code = $LASTEXITCODE }
        else { Log "no gateway folder: analysis skipped" }
        }
    }
    StopWifiProbe
    $status.network_scope_checks = $script:scopeChecks
    if ($Demo -and $status.final_check) {
        # the walkthrough summary reads runner_status.json, so it runs after the Wi-Fi probe has stopped and the status is saved
        Save
        & $py -I "$gw\tools\summarise_live_walkthrough.py" --runner $run 2>&1 | Out-File -Encoding utf8 (Join-Path $run "walkthrough_stdout.txt")
        $status.walkthrough_summary_exit_code = $LASTEXITCODE
    }
    $status.finished = (Get-Date).ToString("o"); Step "done"


}
