# Start one RegoLight participant trial against the DIGITAL TWIN REPO (SIMULATION ONLY; 20 Nov 2026).
#
# From lab_digital_twin (branch albert-phase2-alpha), each in its own window (QuickEdit off, so a click cannot pause it):
#   1. Mohsi's twin server   digital_twin/server.py via uvicorn on 127.0.0.1:8080 (loopback only)
#   2. the Phase 2 trial host  Albert/phase2/trial_host.py on 127.0.0.1:8095 (placements + interventions, request ledger)
#   3. the two view renderers  digital_twin/phase2/vcam_render.py (wrist + site)
# then Remote mode ON, the twin page (operator view) and the S4 participant interface (nominal protocol, facilitator console on
# the right; F9 hides it). The trial: 16 placements, formal CDPs at 5 and 10 (SAGAT RG-2 at 10), inactive potential CDP at 14.
#
#   powershell -ExecutionPolicy Bypass -File C:\Users\a1920234\Documents\Phase2_Interface\twin_link\start_twin_trial.ps1 [-AutoFacilitators] [-Browser]
# 23 Nov 2026: the twin page (operator view) is NOT opened unless -Browser is given. A visible 3D twin page competes with the two
# view renderers for the GPU: measured, it cut the participant views from ~14.6 to ~10.6 fps and nearly doubled their age
# (~64 -> ~115 ms median). Open it only when needed and minimise it afterwards. -NoBrowser is still accepted (no effect).
# Stop: close the participant window, then the three server windows. Only one twin-repo server at a time (it keeps its simulator
# state in digital_twin/models/sim_state.json).
param([switch]$AutoFacilitators, [switch]$Browser, [switch]$NoBrowser, [switch]$InAppConsole)
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $Here
$DT = "C:\Users\a1920234\Documents\Phase 2_COROL\lab_digital_twin\digital_twin"
$DTPy = Join-Path (Split-Path -Parent $DT) ".venv\Scripts\python.exe"
$Unity = Join-Path $Root "unity\Phase2Client"
$S4 = Join-Path $Unity "Builds\S4\SiteWindowSession.exe"
$Protocol = Join-Path $Unity "Assets\Phase2\Experiment\Protocols\phase2_s41_corol_regolight_nominal_taught.json"
$NoQE = Join-Path $Here "console_noquickedit.ps1"

function Wait-Url($url, $seconds) {
    $t0 = Get-Date
    while (((Get-Date) - $t0).TotalSeconds -lt $seconds) {
        try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 $url | Out-Null; return $true } catch { Start-Sleep -Milliseconds 300 }
    }
    return $false
}

foreach ($port in 8080, 8095) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw "port $port is already in use: close the old twin / host first" }
}
foreach ($f in $DTPy, $S4, $Protocol) { if (-not (Test-Path $f)) { throw "missing $f" } }

Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='Twin server (Mohsi, SIMULATION ONLY, 127.0.0.1:8080)'; . '$NoQE'; & '$DTPy' -m uvicorn server:app --host 127.0.0.1 --port 8080" -WorkingDirectory $DT
if (-not (Wait-Url "http://127.0.0.1:8080/api/phase2/objects" 90)) { throw "twin server did not start (see its window)" }
Invoke-RestMethod -Method Post http://127.0.0.1:8080/api/sim/remote -ContentType application/json -Body '{"enabled": true}' | Out-Null
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='Phase 2 trial host (SIMULATION ONLY, 127.0.0.1:8095)'; . '$NoQE'; & '$DTPy' Albert\phase2\trial_host.py" -WorkingDirectory $DT
if (-not (Wait-Url "http://127.0.0.1:8095/api/status" 90)) { throw "trial host did not start (see its window)" }
# 23 Nov 2026: a run stopped while the robot was mid-move leaves an UNKNOWN_OUTCOME in the host's ledger; the host then refuses every
# request (the trial's reset is REJECTED and the trial cannot start). Ask the operator for their account here, before the interface opens.
$st = Invoke-RestMethod http://127.0.0.1:8095/api/status
foreach ($id in @($st.unresolved)) {
    if (-not $id) { continue }
    Write-Host ""
    Write-Host "The trial host is BLOCKED by an earlier request whose outcome was never observed (a run stopped mid-move):" -ForegroundColor Yellow
    Write-Host "  $id" -ForegroundColor Yellow
    $map = @{ u = "undetermined"; c = "completed_as_intended"; n = "not_executed"; p = "partially_executed" }
    $ans = (Read-Host "What happened? [u] undetermined (did not see) / [c] completed as intended / [n] not executed / [p] partially executed / [q] quit").Trim().ToLower()
    if (-not $map.ContainsKey($ans)) { throw "not resolved; the trial cannot start until it is (close the server windows and run this again)" }
    $op = (Read-Host "Your name (operator)").Trim(); if (-not $op) { $op = "researcher" }
    $body = @{ resolution = $map[$ans]; operator = $op; note = "Recorded at launch (start_twin_trial.ps1). Simulation only; nothing re-run; the next trial baseline restores the starting layout." } | ConvertTo-Json
    Invoke-RestMethod -Method Post "http://127.0.0.1:8095/api/requests/$id/resolve" -ContentType application/json -Body $body | Out-Null
    Write-Host "  recorded: $($map[$ans]) by $op" -ForegroundColor Green
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='View renderers: wrist + site (SIMULATION ONLY)'; . '$NoQE'; & '$DTPy' phase2\vcam_render.py --cams wrist --site" -WorkingDirectory $DT
Write-Host "Twin server http://127.0.0.1:8080  (Remote mode ON)   Trial host http://127.0.0.1:8095/api/status"
if ($Browser -and -not $NoBrowser) { Start-Process "http://127.0.0.1:8080/?config=client_config_phase2_experiment.json" }

$sessions = Join-Path $Here "runs\sessions"
$args4 = @("-screen-fullscreen", "0", "-screen-width", "1920", "-screen-height", "1080", "-s4", "-s4Protocol", "`"$Protocol`"", "-s4Corol",
           "-s4CorolHost", "http://127.0.0.1:8095", "-s4Root", "`"$sessions`"", "-s4Viewing",
           "-s3AMode", "virtual", "-s3AVcam", "site", "-s3ASiteRendered", "-s3BMode", "virtual", "-s3BVcam", "wrist", "-s3VcamHost", "http://127.0.0.1:8080", "-s4AskParticipant")   # 20 Nov 2026: the participant identification screen first
if (-not $AutoFacilitators) { $args4 += "-s4Manual" }

# 23 Nov 2026: WEB FACILITATOR CONSOLES (default; -InAppConsole keeps the old docked console instead). A small relay
# (Tools/facilitator_relay/facilitator_relay.py, standard library) serves Facilitator A's and Facilitator B's pages; the participant
# app syncs OUT to it. Three fresh random keys per launch: one for the app, one per facilitator (a key acts for its own role only).
# Bound to 127.0.0.1: on this laptop the three "computers" are the participant window and two browser windows.
if (-not $InAppConsole) {
    function New-Key { -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 22 | ForEach-Object { [char]$_ }) }
    $kApp = New-Key; $kA = New-Key; $kB = New-Key
    if (Get-NetTCPConnection -LocalPort 8096 -State Listen -ErrorAction SilentlyContinue) { throw "port 8096 is already in use: close the old facilitator relay first" }
    $Relay = Join-Path $Unity "Tools\facilitator_relay\facilitator_relay.py"
    $relayLog = Join-Path $Here ("runs\relay_actions_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".jsonl")
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='Facilitator relay (web consoles, 127.0.0.1:8096)'; . '$NoQE'; & '$DTPy' '$Relay' --port 8096 --app-key $kApp --a-key $kA --b-key $kB --log '$relayLog'"
    if (-not (Wait-Url "http://127.0.0.1:8096/api/health" 30)) { throw "facilitator relay did not start (see its window)" }
    $args4 += @("-s4Relay", "http://127.0.0.1:8096", "-s4RelayKey", $kApp)
    $urlA = "http://127.0.0.1:8096/a?k=$kA"; $urlB = "http://127.0.0.1:8096/b?k=$kB"
    Start-Process msedge -ArgumentList "--new-window", $urlA
    Start-Process msedge -ArgumentList "--new-window", $urlB
    Write-Host ""
    Write-Host "Facilitator A console: $urlA" -ForegroundColor Yellow
    Write-Host "Facilitator B console: $urlB" -ForegroundColor Cyan
}
Start-Sleep -Seconds 10     # let both renderers deliver frames before the trial reset checks the views
Start-Process $S4 -ArgumentList $args4 -WorkingDirectory $Unity
Write-Host "Participant interface started. Facilitator consoles: $(if ($InAppConsole) { 'docked on the right (F9 hides)' } else { 'the two browser windows (in-app console: F9)' }). Sessions: $sessions"
