<#
Task 04B orchestrator: one bounded localhost run of publishers A and B, their
receivers, injected faults and a controlled MediaMTX restart.

Defaults = smoke test 3 (60 s; 700 ms burst stall at 15 s; restart at 35 s,
down 3 s). The full first-gate (G1) plan from streaming_poc/README.md:
  -Seconds 660 -Stall 120:300:burst,240:700:burst,360:700:drop -Drop 480:5
  -RestartAt 540 -DownSeconds 5 -Label g1

Order: MediaMTX -> publishers -> receivers (receivers stop on the publisher's
done flag + 3 s drain, capped at Seconds + 100 s).

RESTART TIMING (fixed after smoke test 3): stop and restart happen at their
scheduled clock times (t0 + RestartAt, t0 + RestartAt + DownSeconds). The
safety checks still run between them -- port 8554 free (fast .NET listener
table), config unchanged, no MediaMTX running -- and the restart waits for
them, but if they overrun the scheduled time the lateness is recorded in
restart.json and orchestrator.log ("RESTART LATE"), never silently absorbed.
Slow per-process socket attribution (Get-NetTCPConnection) runs only AFTER
each launch, for the S1 evidence.

RESOURCES: every ~5 s, CPU time and memory of MediaMTX and the four Python
INTERPRETER processes are sampled (resources.csv), plus system-wide CPU and
memory (system.csv; GetSystemTimes / GlobalMemoryStatusEx). The venv's
.venv\Scripts\python.exe is a launcher that starts the real interpreter as a
child (G1 sampled the launchers by mistake), so each launcher's python.exe
child is resolved and recorded in pids.json; if none is found the launcher
itself is sampled and pids.json says so. Network use is taken from the
applications' own byte counters (localhost traffic is not attributable per
process without administrator tools).

KEEP-AWAKE (after G1 was interrupted by Modern Standby): for the run's
duration this script's thread holds SetThreadExecutionState(ES_CONTINUOUS |
ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED) -- a per-process request that
changes no power setting or policy and lapses when the process exits. It is
released in the finally block; keepawake.json records both calls (the release
returns the flags that were still held). Kernel-Power standby events (506/507)
during the run are read (read-only) into cleanup.json. Closing the lid,
pressing the power button or locking the screen can still suspend the system.

END OF RUN: before the cleanup check, the script waits (bounded by
-ExitWaitSeconds) for every publisher and receiver -- launcher AND
interpreter -- to exit (G1's check raced the publishers' post-standby
shutdown). The check then records what is still running; anything left is
stopped only AFTER that record (stopped_after_check), so S8 is not masked.

OPTIONS ADDED FOR TASK 05 T3 (orchestrator v2, 5 Nov 2026; defaults unchanged):
  -Cameras A        start only camera A's publisher and receiver (default A,B)
  -NoRestart        skip ONLY the planned MediaMTX restart; preflight, listener
                    check, keep-awake, supervision, resource sampling and
                    cleanup all still run
  -ExternalProcess  name of a process started by hand (e.g. Phase2M1, the Unity
                    player): MediaMTX is kept up until it exits (bounded by
                    -ExitWaitSeconds), and it is recorded in cleanup.json.
                    v3 (5 Nov, Task 05 T4 preparation): the process is found by
                    name once it appears, sampled like the Python roles
                    (resources.csv role "ext_<name>": CPU time, working set,
                    private memory, threads, handles), and its start and exit
                    times are recorded (cleanup.json "external_process.tracked")
  -PlanOnly         print the launch plan (roles and exact arguments) and exit;
                    launches nothing (regression check of the default plan)

Localhost only. Changes no firewall, network, power or security setting.
Run from the streaming_poc folder:
  powershell -ExecutionPolicy Bypass -File .\run_smoke_restart.ps1 [params]
  powershell -ExecutionPolicy Bypass -File .\run_smoke_restart.ps1 -SelfTest -SelfTestDir <dir>
#>
param(
    [int]$Seconds = 60,
    [string[]]$Stall = @("15:700:burst"),
    [string[]]$Drop = @(),
    [double]$RestartAt = 35,
    [double]$DownSeconds = 3,
    [string]$Label = "smoke3",
    [double]$ExitWaitSeconds = 60,
    [string[]]$Cameras = @("A", "B"),
    [switch]$NoRestart,
    [string]$ExternalProcess = "",
    [switch]$PlanOnly,
    # -SelfTest checks the helper functions only: it launches nothing, opens no
    # port and writes only to the scratch folder given.
    [switch]$SelfTest,
    [string]$SelfTestDir = $env:TEMP
)
$ErrorActionPreference = "Stop"
# "powershell -File" passes "a,b,c" as ONE string: split list parameters here.
# "none" = no stalls / drops ("powershell -File" drops an empty-string argument)
$Stall = @($Stall | ForEach-Object { $_ -split "," } | Where-Object { $_ -and $_ -ne "none" })
$Drop = @($Drop | ForEach-Object { $_ -split "," } | Where-Object { $_ -and $_ -ne "none" })
function ResolveCameras($list) {
    # "A", "A,B", @("A","B") -> ordered unique subset of A, B; anything else is refused
    $c = @($list | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim().ToUpper() } | Where-Object { $_ })
    $bad = @($c | Where-Object { $_ -notin @("A", "B") })
    if ($bad.Count -gt 0 -or $c.Count -eq 0) { throw "-Cameras accepts A and/or B (got '$($list -join ",")')" }
    return @(@("A", "B") | Where-Object { $_ -in $c })
}
$Cameras = ResolveCameras $Cameras
$root = $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
$exe = Join-Path $root "tools\mediamtx_v1.21.3\bin\mediamtx.exe"
$cfg = Join-Path $root "config\mediamtx_localhost.yml"
$verifiedSha = "782145b3fac5a219c6b0312a568b00607671b89f4d1bce6ab492f4d51024940a"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$ev = if ($SelfTest -or $PlanOnly) { Join-Path $SelfTestDir "smoke_selftest_$stamp" } else { Join-Path $root "results\smoke_$stamp" }
$ctl = Join-Path $ev "control"
New-Item -ItemType Directory -Force $ctl | Out-Null
$clock = [System.Diagnostics.Stopwatch]::StartNew()

Add-Type -Namespace Poc -Name Native -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);
[DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
[DllImport("kernel32.dll")] public static extern bool GetSystemTimes(out long idle, out long kernel, out long user);
[StructLayout(LayoutKind.Sequential)] public struct MemStatus {
    public uint dwLength; public uint dwMemoryLoad; public ulong ullTotalPhys; public ulong ullAvailPhys;
    public ulong ullTotalPageFile; public ulong ullAvailPageFile; public ulong ullTotalVirtual;
    public ulong ullAvailVirtual; public ulong ullAvailExtendedVirtual; }
[DllImport("kernel32.dll")] public static extern bool GlobalMemoryStatusEx(ref MemStatus m);
'@
$ES_CONTINUOUS = [Convert]::ToUInt32("80000000", 16)
$ES_AWAKE = [Convert]::ToUInt32("80000003", 16)     # CONTINUOUS | SYSTEM_REQUIRED (1) | DISPLAY_REQUIRED (2)

function UtcNs { [int64]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()) * 1000000 }
# Write-Host, NOT Write-Output: anything written to the pipeline inside a
# function becomes part of its return value. (Smoke test 3 first aborted because
# StartMtx returned @(<log line>, <process>) instead of the process.)
function Note($msg) { $line = "{0} {1}" -f (Get-Date).ToString("HH:mm:ss.fff"), $msg; Add-Content -Path (Join-Path $ev "orchestrator.log") -Value $line; Write-Host $line }
function OnlyProcess($result, $what) {
    $p = @($result | Where-Object { $_ -is [System.Diagnostics.Process] })
    if ($p.Count -ne 1) { throw "$what returned $($p.Count) process objects (expected 1)" }
    return $p[0]
}
function FastPort {
    # .NET listener tables: milliseconds, unlike Get-NetTCPConnection (seconds)
    $ipg = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties()
    $t = @($ipg.GetActiveTcpListeners() | Where-Object { $_.Port -eq 8554 } | ForEach-Object { "$($_.Address):$($_.Port)" })
    $u = @($ipg.GetActiveUdpListeners() | Where-Object { $_.Port -eq 8554 } | ForEach-Object { "$($_.Address):$($_.Port)" })
    return [pscustomobject]@{ tcp_listeners = $t; udp_listeners = $u; free = (($t.Count + $u.Count) -eq 0) }
}
function Preflight($name) {
    $fp = FastPort
    $m = @(Get-Process -Name mediamtx -ErrorAction SilentlyContinue)
    $sha = (Get-FileHash $cfg).Hash.ToLower()
    $o = [ordered]@{ checked_at = (Get-Date).ToString("o"); config_sha256 = $sha; config_unchanged_from_verified = ($sha -eq $verifiedSha);
                     port_8554 = $fp; port_8554_free = $fp.free; mediamtx_already_running = ($m.Count -gt 0); launch_blocked = $false }
    $o | ConvertTo-Json -Depth 4 | Out-File -Encoding utf8 (Join-Path $ev $name)
    return $o
}
function RecordSockets($p, $tag) {
    $socks = @()
    $socks += Get-NetTCPConnection -OwningProcess $p.Id -State Listen -ErrorAction SilentlyContinue | ForEach-Object { [ordered]@{ proto = "TCP"; address = $_.LocalAddress; port = $_.LocalPort; pid = $p.Id } }
    $socks += Get-NetUDPEndpoint -OwningProcess $p.Id -ErrorAction SilentlyContinue | ForEach-Object { [ordered]@{ proto = "UDP"; address = $_.LocalAddress; port = $_.LocalPort; pid = $p.Id } }
    ConvertTo-Json -InputObject @($socks) -Depth 3 | Out-File -Encoding utf8 (Join-Path $ev "listeners_$tag.json")
    Note ("MediaMTX $tag pid=$($p.Id) sockets: " + (($socks | ForEach-Object { "$($_.proto) $($_.address):$($_.port)" }) -join ", "))
}
function StartMtx($tag) {
    $p = Start-Process -FilePath $exe -ArgumentList "`"$cfg`"" -WorkingDirectory $root -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $ev "mediamtx_stdout_$tag.txt") -RedirectStandardError (Join-Path $ev "mediamtx_stderr_$tag.txt")
    $deadline = $clock.Elapsed.TotalSeconds + 5
    do { Start-Sleep -Milliseconds 25; $fp = FastPort } until ((-not $fp.free) -or $p.HasExited -or $clock.Elapsed.TotalSeconds -gt $deadline)
    if ($p.HasExited -or $fp.free) { throw "MediaMTX ($tag) did not start listening (exited=$($p.HasExited))" }
    return $p
}
function StartPy($script, $argList, $tag) {
    Start-Process -FilePath $py -ArgumentList (@($script) + $argList) -WorkingDirectory $root -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $ev "$tag.stdout.txt") -RedirectStandardError (Join-Path $ev "$tag.stderr.txt")
}
$script:nextSample = 0.0
$script:roles = @{}
$script:extProc = $null
$script:extInfo = $null
function TrackExternal($name) {
    # find a hand-started process by name once; keep its handle so the exit time stays readable
    if (-not $name -or $script:extProc) { return }
    $p = @(Get-Process -Name $name -ErrorAction SilentlyContinue | Sort-Object StartTime)[0]
    if (-not $p) { return }
    $null = $p.Handle
    $script:extProc = $p
    $script:roles["ext_$name"] = $p.Id
    $script:extInfo = [ordered]@{ name = $name; pid = $p.Id; start_time = $p.StartTime.ToString("o"); found_at = (Get-Date).ToString("o");
                                  exit_time = $null; exit_code = $null; others_with_same_name = @(Get-Process -Name $name -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne $p.Id } | ForEach-Object { $_.Id }) }
    if (Get-Command Note -ErrorAction SilentlyContinue) { Note "external process '$name' found: pid=$($p.Id) started $($script:extInfo.start_time)" }
}
function ExternalExitInfo {
    if (-not $script:extProc) { return $script:extInfo }
    $script:extProc.Refresh()
    if ($script:extProc.HasExited) {
        $script:extInfo.exit_time = $script:extProc.ExitTime.ToString("o")
        try { $script:extInfo.exit_code = $script:extProc.ExitCode } catch { $script:extInfo.exit_code = "unavailable" }
    }
    return $script:extInfo
}
function Sample {
    TrackExternal $ExternalProcess
    if ($clock.Elapsed.TotalSeconds -lt $script:nextSample) { return }
    $script:nextSample = $clock.Elapsed.TotalSeconds + 5
    $f = Join-Path $ev "resources.csv"
    if (-not (Test-Path $f)) { Add-Content $f "t_s,utc,role,pid,cpu_total_s,working_set_mb,private_mb,threads,handles" }
    foreach ($kv in @($script:roles.GetEnumerator())) {
        $p = Get-Process -Id $kv.Value -ErrorAction SilentlyContinue
        # F formats (no thousands separators): the file is comma-separated
        if ($p) { Add-Content $f ("{0:F2},{1},{2},{3},{4:F3},{5:F1},{6:F1},{7},{8}" -f $clock.Elapsed.TotalSeconds, (Get-Date).ToUniversalTime().ToString("o"), $kv.Key, $p.Id, $p.TotalProcessorTime.TotalSeconds, ($p.WorkingSet64 / 1MB), ($p.PrivateMemorySize64 / 1MB), $p.Threads.Count, $p.HandleCount) }
    }
    SampleSystem
}
$script:sysPrev = $null
function SampleSystem {
    # system-wide CPU busy % (all logical processors) since the previous sample, and memory
    $idle = 0L; $kern = 0L; $user = 0L
    if (-not [Poc.Native]::GetSystemTimes([ref]$idle, [ref]$kern, [ref]$user)) { return }
    $m = New-Object Poc.Native+MemStatus
    $m.dwLength = [System.Runtime.InteropServices.Marshal]::SizeOf($m)
    [Poc.Native]::GlobalMemoryStatusEx([ref]$m) | Out-Null
    $f = Join-Path $ev "system.csv"
    if (-not (Test-Path $f)) { Add-Content $f "t_s,utc,cpu_busy_pct_all_cores,logical_cpus,mem_load_pct,mem_avail_mb,mem_total_mb" }
    $busy = ""
    if ($script:sysPrev) {
        $dTot = ($kern + $user) - ($script:sysPrev[1] + $script:sysPrev[2])   # kernel time includes idle
        $dIdle = $idle - $script:sysPrev[0]
        if ($dTot -gt 0) { $busy = "{0:F2}" -f (100.0 * ($dTot - $dIdle) / $dTot) }
    }
    $script:sysPrev = @($idle, $kern, $user)
    Add-Content $f ("{0:F2},{1},{2},{3},{4},{5:F1},{6:F1}" -f $clock.Elapsed.TotalSeconds, (Get-Date).ToUniversalTime().ToString("o"), $busy, [Environment]::ProcessorCount, $m.dwMemoryLoad, ($m.ullAvailPhys / 1MB), ($m.ullTotalPhys / 1MB))
}
function HoldAwake {
    # per-thread request; ES_CONTINUOUS keeps it until released or the process exits
    $prev = [Poc.Native]::SetThreadExecutionState($ES_AWAKE)
    return [ordered]@{ held_at = (Get-Date).ToString("o"); flags = ("0x{0:X8}" -f $ES_AWAKE); call_ok = ($prev -ne 0);
                       previous_state = ("0x{0:X8}" -f $prev); thread_id = [Poc.Native]::GetCurrentThreadId() }
}
function ReleaseAwake($hold) {
    $prev = [Poc.Native]::SetThreadExecutionState($ES_CONTINUOUS)
    $hold.released_at = (Get-Date).ToString("o")
    $hold.release_call_ok = ($prev -ne 0)
    # the release returns the state that was in force: our flags if the request was held to the end
    $hold.state_at_release = ("0x{0:X8}" -f $prev)
    $hold.held_until_release = ($prev -eq $ES_AWAKE)
    $hold.release_thread_id = [Poc.Native]::GetCurrentThreadId()
    $hold.same_thread = ($hold.release_thread_id -eq $hold.thread_id)
    return $hold
}
function ResolveInterpreter($launcher, $role) {
    # .venv\Scripts\python.exe is a launcher: the interpreter is its python.exe child
    $deadline = $clock.Elapsed.TotalSeconds + 5
    do {
        $kids = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($launcher.Id) AND Name='python.exe'" -ErrorAction SilentlyContinue)
        if ($kids.Count -gt 0) { break }
        Start-Sleep -Milliseconds 50
    } until ($launcher.HasExited -or $clock.Elapsed.TotalSeconds -gt $deadline)
    $self = Get-CimInstance Win32_Process -Filter "ProcessId=$($launcher.Id)" -ErrorAction SilentlyContinue
    $r = [ordered]@{ role = $role; launcher_pid = $launcher.Id; launcher_exe = $(if ($self) { $self.ExecutablePath } else { $null }) }
    if ($kids.Count -eq 1) {
        $r.interpreter_pid = [int]$kids[0].ProcessId; $r.interpreter_exe = $kids[0].ExecutablePath
        $r.interpreter_cmdline = $kids[0].CommandLine; $r.sampled = "interpreter (launcher child)"
    } else {
        $r.interpreter_pid = $launcher.Id; $r.interpreter_exe = $r.launcher_exe
        $r.sampled = "launcher itself ($($kids.Count) python.exe children found)"
    }
    return $r
}
function WaitAllExit($pids, [double]$timeoutS) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    do {
        $alive = @($pids | Where-Object { $_ -and (Get-Process -Id $_ -ErrorAction SilentlyContinue) })
        if ($alive.Count -eq 0) { break }
        Sample
        Start-Sleep -Milliseconds 100
    } while ($sw.Elapsed.TotalSeconds -lt $timeoutS)
    return [ordered]@{ timeout_s = $timeoutS; waited_s = [Math]::Round($sw.Elapsed.TotalSeconds, 2);
                       all_exited = ($alive.Count -eq 0); still_running = $alive }
}
function StandbyEvents($since) {
    # read-only: Kernel-Power 506 (enter Modern Standby) / 507 (exit) since $since
    try {
        return @(Get-WinEvent -FilterHashtable @{ LogName = "System"; ProviderName = "Microsoft-Windows-Kernel-Power"; Id = 506, 507; StartTime = $since } -ErrorAction Stop |
                 ForEach-Object { [ordered]@{ time = $_.TimeCreated.ToString("o"); id = $_.Id; message = ($_.Message -split "`n")[0].Trim() } })
    } catch {
        if ($_.Exception.Message -match "No events were found") { return @() }
        return @([ordered]@{ error = $_.Exception.Message })
    }
}
function WaitUntil([double]$t) {
    # poll the monotonic stopwatch; sample resources while waiting
    while ($clock.Elapsed.TotalSeconds -lt $t) { Sample; $left = $t - $clock.Elapsed.TotalSeconds; if ($left -gt 0) { Start-Sleep -Milliseconds ([int][Math]::Min(100, [Math]::Max(1, $left * 1000))) } }
}

function LaunchPlan($cams, $ctlDir) {
    # Exact publisher / receiver arguments (unchanged from the G1 rerun for the default A,B)
    $common = @("--seconds", "$Seconds", "--frame-end", "sei", "--reconnect-max-s", "1.0")
    foreach ($s in $Stall) { $common += @("--stall", $s) }
    foreach ($d in $Drop) { $common += @("--drop", $d) }
    $rxCommon = @("--seconds", "$($Seconds + 100)", "--drain-s", "3", "--reconnect-max-s", "1.0", "--save-every", "200", "--probe-raw")
    $plan = @()
    foreach ($c in $cams) { $plan += [pscustomobject]@{ role = "pub_$c"; script = "publish_synthetic.py"; args = @(@("--camera", $c, "--label", "${Label}_$c", "--done-flag", (Join-Path $ctlDir "$c.done")) + $common) } }
    foreach ($c in $cams) { $plan += [pscustomobject]@{ role = "rx_$c"; script = "receive_reference.py"; args = @(@("--camera", $c, "--label", "${Label}_$c", "--done-flag", (Join-Path $ctlDir "$c.done")) + $rxCommon) } }
    return $plan
}

if ($PlanOnly) {
    $plan = [ordered]@{ cameras = $Cameras; restart = $(if ($NoRestart) { "disabled" } else { "at $RestartAt s, down $DownSeconds s" });
                        external_process = $ExternalProcess; launches = @(LaunchPlan $Cameras "<control>") }
    $plan | ConvertTo-Json -Depth 5
    Remove-Item -Recurse -Force $ev
    exit 0
}

if ($SelfTest) {
    function Probe { Note "inside a function"; return (Get-Process -Id $PID) }
    $r = Probe
    $ok1 = $r -is [System.Diagnostics.Process]
    $ok2 = (OnlyProcess $r "Probe").Id -eq $PID
    $threw = $false; try { OnlyProcess @("text", 1) "bad" | Out-Null } catch { $threw = $true }
    $ok3 = (UtcNs) -gt 1700000000000000000
    $sw = [System.Diagnostics.Stopwatch]::StartNew(); $fp = FastPort; $fpMs = $sw.Elapsed.TotalMilliseconds
    $ok4 = ($fpMs -lt 1000) -and ($fp.PSObject.Properties.Name -contains "free")
    $target = $clock.Elapsed.TotalSeconds + 0.5; WaitUntil $target; $errMs = ($clock.Elapsed.TotalSeconds - $target) * 1000
    $ok5 = ($errMs -ge 0) -and ($errMs -lt 60)
    $script:roles = @{ selftest = $PID }; $script:nextSample = 0; Sample; $ok6 = (Get-Content (Join-Path $ev "resources.csv")).Count -eq 2
    # keep-awake: held, still in force at release, released, same thread
    $hold = HoldAwake
    $rel = ReleaseAwake $hold
    $after = [Poc.Native]::SetThreadExecutionState($ES_CONTINUOUS)
    $ok7 = $hold.call_ok -and $rel.release_call_ok -and $rel.held_until_release -and $rel.same_thread -and ($after -eq $ES_CONTINUOUS)
    # system-wide CPU and memory: second sample has a busy % in 0..100
    Start-Sleep -Milliseconds 300; SampleSystem
    $sysRows = @(Import-Csv (Join-Path $ev "system.csv"))
    $last = $sysRows[-1]
    $ok8 = ($sysRows.Count -ge 2) -and ($last.cpu_busy_pct_all_cores -ne "") -and ([double]$last.cpu_busy_pct_all_cores -ge 0) -and ([double]$last.cpu_busy_pct_all_cores -le 100) -and ([double]$last.mem_total_mb -gt 0) -and ([int]$last.logical_cpus -ge 1)
    # interpreter resolution and the bounded exit wait, on two short local sleeps (no network)
    $short = Start-Process -FilePath $py -ArgumentList "-I -c `"import time; time.sleep(6)`"" -PassThru -WindowStyle Hidden
    $long = Start-Process -FilePath $py -ArgumentList "-I -c `"import time; time.sleep(60)`"" -PassThru -WindowStyle Hidden
    $swr = [System.Diagnostics.Stopwatch]::StartNew(); $rs = ResolveInterpreter $short "short"; $resolveMs = $swr.Elapsed.TotalMilliseconds; $rl = ResolveInterpreter $long "long"
    $ok9 = ($rs.sampled -like "interpreter*") -and ($rs.interpreter_pid -ne $rs.launcher_pid) -and ($rs.interpreter_exe -ne $rs.launcher_exe) -and ($rl.sampled -like "interpreter*")
    $script:roles = @{ short = $rs.interpreter_pid }; $script:nextSample = 0; Sample
    $ip = @(Import-Csv (Join-Path $ev "resources.csv") | Where-Object { $_.role -eq "short" })
    $ok9 = $ok9 -and ($ip.Count -eq 1) -and ([int]$ip[0].pid -eq $rs.interpreter_pid)
    $w1 = WaitAllExit @($rs.launcher_pid, $rs.interpreter_pid) 10
    $w2 = WaitAllExit @($rl.launcher_pid, $rl.interpreter_pid) 1
    $ok10 = $w1.all_exited -and ($w1.waited_s -ge 0.5) -and ($w1.waited_s -lt 10) -and (-not $w2.all_exited) -and ($w2.waited_s -ge 1.0) -and ($w2.waited_s -lt 3) -and (@($w2.still_running).Count -eq 2)
    foreach ($id in @($rl.interpreter_pid, $rl.launcher_pid)) { Stop-Process -Id $id -Confirm:$false -ErrorAction SilentlyContinue }
    $w3 = WaitAllExit @($rl.launcher_pid, $rl.interpreter_pid) 5
    $ok10 = $ok10 -and $w3.all_exited
    # orchestrator v2 options: camera selection, launch plan, restart switch
    $okC = ((ResolveCameras @("A", "B")) -join ",") -eq "A,B" -and ((ResolveCameras "A") -join ",") -eq "A" -and ((ResolveCameras "B") -join ",") -eq "B" -and ((ResolveCameras "b,a,A") -join ",") -eq "A,B"
    $threwC = $false; try { ResolveCameras "C" | Out-Null } catch { $threwC = $true }
    $threwE = $false; try { ResolveCameras "" | Out-Null } catch { $threwE = $true }
    $pA = @(LaunchPlan @("A") "ctl"); $pAB = @(LaunchPlan @("A", "B") "ctl")
    $okP = ($pA.Count -eq 2) -and (($pA | ForEach-Object { $_.role }) -join ",") -eq "pub_A,rx_A" -and ($pAB.Count -eq 4) -and (($pAB | ForEach-Object { $_.role }) -join ",") -eq "pub_A,pub_B,rx_A,rx_B" -and ($pA[0].args -join " ") -eq ($pAB[0].args -join " ")
    $ok12 = $okC -and $threwC -and $threwE -and $okP
    # v3: external process found by name, sampled, exit time recorded; empty lists serialise as []
    $ping = Start-Process -FilePath "$env:SystemRoot\System32\PING.EXE" -ArgumentList "-n 4 127.0.0.1" -PassThru -WindowStyle Hidden
    Start-Sleep -Milliseconds 300
    $script:roles = @{}; TrackExternal "PING"
    $script:nextSample = 0; Sample
    $extRow = @(Import-Csv (Join-Path $ev "resources.csv") | Where-Object { $_.role -eq "ext_PING" })
    $ping.WaitForExit(10000) | Out-Null
    $xi = ExternalExitInfo
    # same form as the cleanup record's external_process_running (array held in a variable)
    $noSuch = "NoSuchProcess_phase2_xyz"
    $extLeftTest = @(if ($noSuch) { Get-Process -Name $noSuch -ErrorAction SilentlyContinue | ForEach-Object { $_.Id } })
    $emptyJson = ([ordered]@{ running = $extLeftTest } | ConvertTo-Json -Compress)
    $ok13 = ($xi.pid -eq $ping.Id) -and ($extRow.Count -ge 1) -and ([int]$extRow[0].pid -eq $ping.Id) -and [bool]$xi.exit_time -and ($emptyJson -eq '{"running":[]}')
    $script:extProc = $null; $script:extInfo = $null; $script:roles = @{}
    $se = @(StandbyEvents (Get-Date).AddDays(-1))
    $ok11 = -not ($se | Where-Object { $_.Contains("error") })
    Write-Host "SELFTEST function returns only the process: $ok1"
    Write-Host "SELFTEST OnlyProcess passes a single process: $ok2"
    Write-Host "SELFTEST OnlyProcess rejects a non-process result: $threw"
    Write-Host "SELFTEST UtcNs plausible: $ok3"
    Write-Host ("SELFTEST fast port check returns in {0:N0} ms (< 1000): {1}  (8554 free now: {2})" -f $fpMs, $ok4, $fp.free)
    Write-Host ("SELFTEST WaitUntil overshoot {0:N1} ms (0..60): {1}" -f $errMs, $ok5)
    Write-Host "SELFTEST resource sample written: $ok6"
    Write-Host ("SELFTEST keep-awake held to release, released, same thread: {0}  (hold prev {1}, at release {2}, after {3:X8})" -f $ok7, $rel.previous_state, $rel.state_at_release, $after)
    Write-Host ("SELFTEST system CPU/memory sampled: {0}  (busy {1} %, {2} CPUs, mem {3} %)" -f $ok8, $last.cpu_busy_pct_all_cores, $last.logical_cpus, $last.mem_load_pct)
    Write-Host ("SELFTEST interpreter child resolved and sampled: {0}  (in {5:N0} ms; launcher {1} {2} -> interpreter {3} {4})" -f $ok9, $rs.launcher_pid, $rs.launcher_exe, $rs.interpreter_pid, $rs.interpreter_exe, $resolveMs)
    Write-Host ("SELFTEST bounded exit wait (exited after {0} s; timeout honoured at {1} s with {2} alive; stopped): {3}" -f $w1.waited_s, $w2.waited_s, @($w2.still_running).Count, $ok10)
    Write-Host ("SELFTEST standby event query (read-only) ran: {0}  ({1} Kernel-Power 506/507 events in the last 24 h)" -f $ok11, $se.Count)
    Write-Host ("SELFTEST external process found by name, sampled (CPU/memory row), exit time recorded; empty list serialises as []: {0}  (pid {1}, exit {2}, json {3})" -f $ok13, $xi.pid, $xi.exit_time, $emptyJson)
    Write-Host ("SELFTEST -Cameras parsing (A,B / A / B / order; C and empty refused) and launch plans (A: pub_A,rx_A; A,B: 4, same camera-A args): {0}" -f $ok12)
    Write-Host ("SELFTEST " + $(if ($ok1 -and $ok2 -and $threw -and $ok3 -and $ok4 -and $ok5 -and $ok6 -and $ok7 -and $ok8 -and $ok9 -and $ok10 -and $ok11 -and $ok12 -and $ok13) { "PASS" } else { "FAIL" }))
    Remove-Item -Recurse -Force $ev
    exit 0
}

$restart = [ordered]@{ plan = [ordered]@{ seconds = $Seconds; stalls = $Stall; drops = $Drop; restart_at_s = $(if ($NoRestart) { $null } else { $RestartAt }); down_s = $DownSeconds; label = $Label;
                                         cameras = $Cameras; no_restart = [bool]$NoRestart; external_process = $ExternalProcess; orchestrator = "v2" } }
$procs = @()
$interp = @()
$mtx = $null
$runStart = Get-Date
$awake = HoldAwake
try {
    $awake | ConvertTo-Json -Depth 3 | Out-File -Encoding utf8 (Join-Path $ev "keepawake.json")
    Note "evidence folder $ev"
    Note ("keep-awake request held (flags {0}, call ok {1}, thread {2})" -f $awake.flags, $awake.call_ok, $awake.thread_id)
    if (-not $awake.call_ok) { throw "SetThreadExecutionState keep-awake request failed" }
    $pre = Preflight "preflight.json"
    if (-not $pre.config_unchanged_from_verified) { throw "config differs from the verified version" }
    if (-not $pre.port_8554_free -or $pre.mediamtx_already_running) { throw "port 8554 not free or MediaMTX already running" }
    Get-CimInstance Win32_Process -Filter "ProcessId=$PID" | Out-Null    # warm up WMI before the timed launches
    SampleSystem                                                          # baseline for the first system CPU delta
    $mtx = OnlyProcess (StartMtx "first") "StartMtx first"
    $restart.first_pid = $mtx.Id
    $script:roles["mediamtx"] = $mtx.Id
    RecordSockets $mtx "first"
    Start-Sleep -Seconds 1

    $plan = @(LaunchPlan $Cameras $ctl)
    $launched = [ordered]@{}
    foreach ($e in @($plan | Where-Object { $_.role -like "pub_*" })) { $launched[$e.role] = OnlyProcess (StartPy $e.script $e.args $e.role) $e.role }
    $t0 = $clock.Elapsed.TotalSeconds
    $restart.publishers_started_utc_ns = UtcNs
    $procs = @($launched.Values)
    Note ("publishers started (cameras {0}; launchers {1})" -f ($Cameras -join ","), (($launched.Keys | ForEach-Object { "$_ pid=$($launched[$_].Id)" }) -join ", "))
    WaitUntil ($t0 + 1.5)
    foreach ($e in @($plan | Where-Object { $_.role -like "rx_*" })) { $launched[$e.role] = OnlyProcess (StartPy $e.script $e.args $e.role) $e.role }
    $procs = @($launched.Values)
    Note ("receivers started ({0})" -f ((@($launched.Keys | Where-Object { $_ -like "rx_*" }) | ForEach-Object { "$_ pid=$($launched[$_].Id)" }) -join ", "))
    # interpreter PIDs are resolved only now (WMI takes ~1.5 s each here), so the
    # launch timeline is unchanged from G1
    foreach ($pair in @($launched.Keys | ForEach-Object { , @($launched[$_], $_) })) {
        $r = ResolveInterpreter $pair[0] $pair[1]
        $interp += $r
        $script:roles[$pair[1]] = $r.interpreter_pid
        Note "$($pair[1]) interpreter pid=$($r.interpreter_pid) [$($r.sampled)]"
        Sample
    }
    ConvertTo-Json -InputObject @($interp) -Depth 3 | Out-File -Encoding utf8 (Join-Path $ev "pids.json")

    # --- controlled restart, on the scheduled clock (skipped with -NoRestart) ---
    if ($NoRestart) {
        $restart.restart = "disabled (-NoRestart)"
        Note "MediaMTX restart DISABLED (-NoRestart); all other checks unchanged"
    } else {
    $stopAt = $t0 + $RestartAt
    $startAt = $stopAt + $DownSeconds
    $restart.planned_stop_t_s = $RestartAt
    $restart.planned_start_t_s = $RestartAt + $DownSeconds
    WaitUntil $stopAt
    $restart.stop_issued_utc_ns = UtcNs
    $restart.stop_issued_t_s = [Math]::Round($clock.Elapsed.TotalSeconds - $t0, 3)
    Stop-Process -Id $mtx.Id -Confirm:$false
    $mtx.WaitForExit(3000) | Out-Null
    do { Start-Sleep -Milliseconds 20; $fp = FastPort } until ($fp.free -or $clock.Elapsed.TotalSeconds -gt $startAt + 10)
    $restart.port_closed_utc_ns = UtcNs
    $restart.port_closed_t_s = [Math]::Round($clock.Elapsed.TotalSeconds - $t0, 3)
    $restart.port_closed = $fp.free
    Note ("MediaMTX stopped (pid=$($mtx.Id)) at t={0:N2}s; port closed={1} at t={2:N2}s" -f $restart.stop_issued_t_s, $fp.free, $restart.port_closed_t_s)
    $pre2 = Preflight "preflight_restart.json"
    if (-not $pre2.port_8554_free -or $pre2.mediamtx_already_running -or -not $pre2.config_unchanged_from_verified) { throw "pre-restart check failed" }
    $restart.checks_done_t_s = [Math]::Round($clock.Elapsed.TotalSeconds - $t0, 3)
    $late = $clock.Elapsed.TotalSeconds - $startAt
    if ($late -gt 0) {
        $restart.restart_late_by_s = [Math]::Round($late, 3)
        Note ("RESTART LATE by {0:N3} s: the safety checks finished after the scheduled time" -f $late)
    } else {
        WaitUntil $startAt
        $restart.restart_late_by_s = 0
    }
    $restart.start_issued_utc_ns = UtcNs
    $restart.start_issued_t_s = [Math]::Round($clock.Elapsed.TotalSeconds - $t0, 3)
    $mtx = OnlyProcess (StartMtx "restart") "StartMtx restart"
    $restart.listening_again_utc_ns = UtcNs
    $restart.listening_again_t_s = [Math]::Round($clock.Elapsed.TotalSeconds - $t0, 3)
    $restart.restart_pid = $mtx.Id
    $script:roles["mediamtx"] = $mtx.Id
    Note ("MediaMTX restart issued at t={0:N3}s (planned {1}), listening at t={2:N3}s" -f $restart.start_issued_t_s, ($RestartAt + $DownSeconds), $restart.listening_again_t_s)
    RecordSockets $mtx "restart"
    }

    # --- wait for the run to finish --------------------------------------------
    $endBy = $clock.Elapsed.TotalSeconds + $Seconds + 150
    while (($procs | Where-Object { -not $_.HasExited }) -and $clock.Elapsed.TotalSeconds -lt $endBy) { Sample; Start-Sleep -Milliseconds 200 }
    $restart.all_python_exited = -not ($procs | Where-Object { -not $_.HasExited })
    Note ("python processes exited: " + $restart.all_python_exited)
}
catch {
    Note ("ABORTED: " + $_.Exception.Message)
    $restart.aborted = $_.Exception.Message
    # stop interpreters as well as launchers: stopping a launcher alone orphans its interpreter
    foreach ($i in $interp) { if ($i.interpreter_pid -ne $i.launcher_pid) { Stop-Process -Id $i.interpreter_pid -Confirm:$false -ErrorAction SilentlyContinue } }
    foreach ($p in $procs) { if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Confirm:$false -ErrorAction SilentlyContinue } }
}
finally {
    try {
        # every publisher and receiver (launcher and interpreter) must have exited before the check
        $pyPids = @($procs | ForEach-Object { $_.Id }) + @($interp | ForEach-Object { $_.interpreter_pid })
        $exitWait = WaitAllExit ($pyPids | Select-Object -Unique) $ExitWaitSeconds
        Note ("python exit wait: all exited={0} after {1} s (timeout {2} s); still running: {3}" -f $exitWait.all_exited, $exitWait.waited_s, $ExitWaitSeconds, ($exitWait.still_running -join ","))
        $extWait = $null
        if ($ExternalProcess) {
            # MediaMTX stays up until the hand-started process (e.g. the Unity player) has exited
            TrackExternal $ExternalProcess
            $extPids = @(@(Get-Process -Name $ExternalProcess -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }) + @($script:extInfo | Where-Object { $_ } | ForEach-Object { $_.pid }) | Select-Object -Unique)
            $extWait = WaitAllExit $extPids $ExitWaitSeconds
            $extWait.name = $ExternalProcess; $extWait.pids_seen = $extPids; $extWait.tracked = ExternalExitInfo
            Note ("external process '{0}' exit wait: pids [{1}], all exited={2} after {3} s" -f $ExternalProcess, ($extPids -join ","), $extWait.all_exited, $extWait.waited_s)
        }
        if ($mtx -and -not $mtx.HasExited) { Stop-Process -Id $mtx.Id -Confirm:$false; $mtx.WaitForExit(5000) | Out-Null; Note "MediaMTX stopped (end, pid=$($mtx.Id))" }
        $restart | ConvertTo-Json -Depth 4 | Out-File -Encoding utf8 (Join-Path $ev "restart.json")
        Start-Sleep -Milliseconds 700
        $fp = FastPort
        $other = @(Get-NetTCPConnection -LocalPort 8554 -ErrorAction SilentlyContinue | Where-Object { $_.State -ne "Listen" } | ForEach-Object { "$($_.State)" } | Group-Object | ForEach-Object { "$($_.Name) x$($_.Count)" })
        $left = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'publish_synthetic|receive_reference' } | ForEach-Object { $_.ProcessId })
        # an array held in a variable serialises as [] when empty (an inline $(if ...) expression became {} in T3)
        $extLeft = @(if ($ExternalProcess) { Get-Process -Name $ExternalProcess -ErrorAction SilentlyContinue | ForEach-Object { $_.Id } })
        $post = [ordered]@{ checked_at = (Get-Date).ToString("o"); mediamtx_running = (@(Get-Process -Name mediamtx -ErrorAction SilentlyContinue).Count -gt 0);
                            port_8554_listening = (-not $fp.free); port_8554 = $fp; port_8554_other_tcp = $other; poc_python_pids = $left;
                            python_exit_wait = $exitWait;
                            external_process = $extWait;
                            external_process_running = $extLeft;
                            orchestrator_aborted = [bool]$restart.aborted;
                            # a security block is recorded only if a launch was refused by Windows; the
                            # script cannot see GUI prompts (operator confirmation is separate)
                            launch_blocked = $false }
        # anything still running is stopped only AFTER it has been recorded (S8 stays honest)
        $post.stopped_after_check = @($left | ForEach-Object { Stop-Process -Id $_ -Confirm:$false -ErrorAction SilentlyContinue; $_ })
        $post.standby_events_during_run = @(StandbyEvents $runStart)
        $post | ConvertTo-Json -Depth 4 | Out-File -Encoding utf8 (Join-Path $ev "cleanup.json")
        if ($post.standby_events_during_run.Count) { Note ("STANDBY EVENTS DURING RUN: " + (($post.standby_events_during_run | ForEach-Object { "$($_.id)@$($_.time)" }) -join ", ")) }
        if (Test-Path (Join-Path $root "results\mediamtx.log")) { Move-Item (Join-Path $root "results\mediamtx.log") (Join-Path $ev "mediamtx.log") -Force }
    }
    finally {
        $awake = ReleaseAwake $awake
        $awake | ConvertTo-Json -Depth 3 | Out-File -Encoding utf8 (Join-Path $ev "keepawake.json")
        Note ("keep-awake released (held to release: {0}; state at release {1}; same thread: {2})" -f $awake.held_until_release, $awake.state_at_release, $awake.same_thread)
        Note "cleanup recorded; EVIDENCE=$ev"
    }
}
