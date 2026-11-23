# Task 03 camera validation: runbook

Standalone camera checks for the Phase 2 OAK-D Pro PoE (wrist) and OAK-D Pro W PoE (overview).
No robot-control, Unity or streaming code. Nothing here writes camera firmware, bootloader, EEPROM or calibration.
All outputs go to `results/`.

## One-time setup (on Wi-Fi) - done 3 Nov 2026

Python 3.13.17 installed per-user from the signed python.org installer (no PATH changes, no launcher):
`%LOCALAPPDATA%\Programs\Python\Python313\python.exe`. Packages live only in `.venv`.

```powershell
cd C:\Users\a1920234\Documents\Phase2_Interface\camera_validation
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe env_check.py
```

## On the isolated camera network (Ethernet only)

Laptop -> Ethernet 4 -> PoE switch -> PoE port -> camera. Wait about 20-30 s after plugging the camera in for it to boot.

### Verified setup (3 Nov 2026, each camera tested individually)

| | Value |
|---|---|
| Laptop adapter | `Ethernet 4`, Realtek USB GbE Family Controller #3 (via HP USB-C Dock G5), 1 Gbps |
| Laptop IPv4 | `169.254.80.246/16` (link-local; there is no DHCP on the camera network) |
| Camera A | OAK-D Pro PoE AF (wrist, provisional): `169.254.1.222`, ID `19443010B14C872F00`, MAC `44-A9-2C-32-3C-AC` |
| Camera B | OAK-D Pro W PoE (overview, provisional): `169.254.1.223`, ID `194430108183F12E00`, MAC `44-A9-2C-37-BA-5D` |

The university Wi-Fi appears to drop when Ethernet is active (cause unconfirmed; IT request in progress). Prepare scripts on Wi-Fi, run them on Ethernet, then reconnect to review `results/`.
Full details and evidence: [CAMERA_DISCOVERY_2026-11-03.md](CAMERA_DISCOVERY_2026-11-03.md).

```powershell
cd C:\Users\a1920234\Documents\Phase2_Interface\camera_validation
powershell -ExecutionPolicy Bypass -File .\net_check.ps1 -CameraIp 169.254.1.222
.venv\Scripts\python.exe discover_cameras.py --ip 169.254.1.222
.venv\Scripts\python.exe discover_cameras.py --broadcast --no-connect
```

Camera B alone: replace `169.254.1.222` with `169.254.1.223`.

> **4 Nov 2026:** with both cameras attached, `--ip 169.254.1.222` first failed and once booted Camera B instead, while Windows mapped `.222` to Camera B's MAC. After a switch-port swap, sequential `--ip` connections to both cameras passed; the cause is not confirmed. With both cameras attached, **use the verified `--expect` mode below, not `--ip`**. If a connection fails or returns the wrong ID, run the ARP check in [CAMERA_DISCOVERY_2026-11-03.md §6.6](CAMERA_DISCOVERY_2026-11-03.md) first.

Both cameras together, verified mode (**passed 14:55, 4 Nov**: both held open together for 10 s, `RESULT: PASS`; see checkpoint §6.9):

```powershell
powershell -ExecutionPolicy Bypass -File .\net_check.ps1 -CameraIp 169.254.1.222,169.254.1.223
.venv\Scripts\python.exe discover_cameras.py --expect 169.254.1.222=19443010B14C872F00 --expect 169.254.1.223=194430108183F12E00 --hold-seconds 10
```

`--expect` boots nothing unless broadcast discovery shows each expected camera exactly once, at its IP, with its device ID, in bootloader state. After connecting it rejects and closes any connection whose ID or IP differs. It then holds the verified connections open together and closes them all, even if one fails. The log ends `RESULT: PASS` or `RESULT: FAIL`. The older `--simultaneous` mode checks the IP only.

### Stage C: stereo capture, one camera

Initial functional validation is complete for both cameras (4 Nov, checkpoint §7.8). Continuity is measured in Stage D.

```powershell
.venv\Scripts\python.exe calibration_check.py --expect 169.254.1.222=19443010B14C872F00 --baseline-user results\calibration_user_19443010B14C872F00_20261103_182445.json --baseline-factory results\calibration_factory_19443010B14C872F00_20261103_182445.json
.venv\Scripts\python.exe capture_stereo.py --expect 169.254.1.222=19443010B14C872F00 --preview --baseline-user results\calibration_user_19443010B14C872F00_20261103_182445.json --baseline-factory results\calibration_factory_19443010B14C872F00_20261103_182445.json
```

DepthAI 3.11.0's `pipeline.stop()` closes the device. `capture_stereo.py` therefore re-reads calibration before stopping, and again through a fresh read-only connection afterwards.

### Stage D: frame continuity (**completed 4 Nov**, D1–D7; findings in checkpoint §9)

Stalls occur at the transport level, not in the laptop's queue. Frames are lost only when a stall exceeds about 6–7 frames. The `tcp_*` network counters are the laptop's own and cannot show retransmissions by the camera.

```powershell
$A = "--expect","169.254.1.222=19443010B14C872F00","--baseline-user","results\calibration_user_19443010B14C872F00_20261103_182445.json","--baseline-factory","results\calibration_factory_19443010B14C872F00_20261103_182445.json"
$B = "--expect","169.254.1.223=194430108183F12E00","--baseline-user","results\calibration_user_194430108183F12E00_20261103_183335.json","--baseline-factory","results\calibration_factory_194430108183F12E00_20261103_183335.json"
$D = "--pairs","1200","--max-seconds","120","--save-pairs","3","--network-stats"
.venv\Scripts\python.exe capture_stereo.py @A @D --label D1_A_sync
```

Each run reports the functional `RESULT` and, separately, `CONTINUITY` (missing frames, gaps, and per-sensor losses in `--pairing host-seq`).

- **What it does:** selects the camera the Stage B way, then streams CAM_B/CAM_C at native 1280 × 800, 20 fps, GRAY8, paired by a DepthAI `Sync` node (threshold: half the frame period). It does no undistortion, resizing, rectification or depth. It collects 200 pairs and saves 5 representative left/right/side-by-side PNGs.
- **Output:** `results/stereo_<timestamp>_<deviceId>/` (`report.json`, `pairs.csv`, `capture.log`, `images/`).
- **Refuses to start** unless IR off is acknowledged and `AutoCalibrationMode` is confirmed `OFF`. DepthAI's default would run auto-calibration and may flash user calibration.
- **Always** stops the pipeline, re-checks the calibration hash and closes the device.

For Camera B, use `--expect 169.254.1.223=194430108183F12E00`. Details and expected behaviour: [checkpoint §7](CAMERA_DISCOVERY_2026-11-03.md).

### Stage E: rectification and geometry (**E1–E5 complete 4 Nov**; checkpoint §11–12)

Provisional configuration (**approved by the researcher**):
- **Both cameras:** distortion correction explicitly `on`, alpha unset. These are the `rectify_stereo.py` defaults.
- **Camera A crop:** inclusive x 39–1276, y 6–775 = `img[6:776, 39:1277]` (1238 × 770), for both eyes and the 2D view.
- **Camera B:** no crop. Do not use alpha 0, which produces non-square pixels.

Second-scene test E6–E9 (prepared, **not yet run**), with a live setup preview. `--setup-preview` passed 38 offline checks but is **untested with a physical camera or real OpenCV window**. Start with E6 alone, following [NEXT SESSION: START HERE](CAMERA_DISCOVERY_2026-11-03.md#next-session-start-here), which has the full E6–E9 commands and the check to do between E6 and E7.

```powershell
$S = "--groups","60","--warmup-groups","30","--save-groups","10","--setup-preview"
.venv\Scripts\python.exe rectify_stereo.py @B @S --label E6_B_s2_mixed
.venv\Scripts\python.exe rectify_stereo.py @A @S --preview-crop 39,6,1276,775 --label E8_A_s2_mixed
```

**Preview keys:**
- **Space** starts the normal capture.
- **G** toggles the 5 × 5 grid and per-cell texture counts (and the crop outline).
- **Q or Esc** cancels (`RESULT: CANCELLED`, nothing captured).

Overlays are display-only and never saved.

The full procedure, analysis commands and CRATER coverage check are in checkpoint §12.4–12.6. Analysis: `analyse_epipolar.py`. Coverage: `coverage_check.py generate | analyse`.

```powershell
$A = "--expect","169.254.1.222=19443010B14C872F00","--baseline-user","results\calibration_user_19443010B14C872F00_20261103_182445.json","--baseline-factory","results\calibration_factory_19443010B14C872F00_20261103_182445.json"
$B = "--expect","169.254.1.223=194430108183F12E00","--baseline-user","results\calibration_user_194430108183F12E00_20261103_183335.json","--baseline-factory","results\calibration_factory_194430108183F12E00_20261103_183335.json"
.venv\Scripts\python.exe rectify_stereo.py @A --label E1_A_default
```

5 fps, native 1280 × 800, `StereoDepth` rectification with distortion correction explicit. A group is formed only when raw and rectified left/right all carry the same sequence number. Geometry is analysed after shutdown (`GEOMETRY:` line, `geometry.json`). Offline analysis of saved raw pairs: `stereo_geometry.py --calibration <user.json> --pair <left.png> <right.png>`.

| Script | Touches camera? | Purpose |
|---|---|---|
| `env_check.py` | No | Python/package versions, DepthAI API availability |
| `net_check.ps1` | Ping + TCP 11490 only | Adapter state, link-local addressing, reachability |
| `discover_cameras.py` | Connects (runtime firmware into RAM only); `--broadcast --no-connect` only discovers | IDs, product, sensors, bootloader version, IR drivers, calibration (read-only copy saved to `results/`); `--expect`: verified connection and concurrent hold. Reports any new DepthAI crash dump. |
| `capture_stereo.py` | Connects and streams mono frames (no IR, auto-calibration OFF); reconnects read-only afterwards | Stage C synchronised stereo capture, timing, sequence and image records, calibration verified by content |
| `calibration_check.py` | Connects read-only, no pipeline | User and factory calibration read and compared by content with saved baselines |
| `stereo_geometry.py` | No | Host geometry analysis; offline mode for saved raw pairs |
| `rectify_stereo.py` | Connects and streams raw + rectified (no IR, auto-calibration OFF); reconnects read-only afterwards | Stage E rectification capture and geometry report; optional `--setup-preview` for positioning targets |
| `analyse_stage_e.py` | No | Offline E1–E5 re-analysis: misalignment model, outliers, borders, model check, cross-run mapping |
| `analyse_epipolar.py` | No | Cross-scene offset/roll/scale with 95% intervals, 5 × 5 coverage, crop check, held-out evaluation of candidate corrections |
| `coverage_check.py` | No | Printable ArUco markers; coverage and edge margins from a saved run |
