# Camera validation checkpoint: Task 03 (3–4 November 2026)

Every hardware result below comes from the machine-generated files listed under [Evidence](#evidence). Items marked *(user-reported)* are not in those files. Sections 1–12 are a chronological record: section headings marked as historical describe what was planned at the time. **For current status and how to resume, see [Handover status](#handover-status-end-of-4-november-2026) and [NEXT SESSION: START HERE](#next-session-start-here) at the end.**

**Status at the end of 4 November 2026:**

| Stage | Status |
|---|---|
| A: environment | Complete |
| B: discovery, both cameras on one network | Complete (verified concurrent connection, §6.9). The earlier address-resolution failures have no confirmed root cause. |
| C: stereo acquisition | Initial functional validation complete for both cameras (§7.8). The 15:22/15:23 runs remain recorded as FAIL (§7.5). |
| D: synchronisation and continuity | Complete (D1–D7, §9). Synchronisation verified; intermittent delivery stalls, root cause unknown. |
| E: rectification | E1–E5 complete and analysed (§11). Provisional configuration approved (§12.1). **E6–E9 prepared, not run** (§12.4–12.7). The `--setup-preview` mode is validated offline only. |
| F: image quality, G: final report | Not started |

See [§6](#6-4-november-update-both-cameras-on-the-switch) for the Stage B address issue and [§6.9](#69-stage-b-concurrent-connection-passed-1455) for its pass.

---

## 1. Development machine

| Item | Value | Source |
|---|---|---|
| Hostname | AU-350998 | `net_check` transcript |
| OS | Windows 11 Enterprise (NT 10.0.26200) | `net_check` transcript, `env_check` |
| Dock | HP USB-C Dock G5 | *(user-reported)* |
| Ethernet adapter | Realtek USB GbE Family Controller #3 (`Ethernet 4`) | `net_check` transcript |
| Ethernet link | 1 Gbps, Connected | `net_check` transcript |
| Laptop Ethernet IPv4 | `169.254.80.246/16` (link-local, `WellKnown`; no DHCP on the camera network) | `net_check` transcript, discovery logs |
| Network | Isolated PoE switch; cameras connected over Ethernet/PoE | *(user-reported)* |
| Python | 3.13.17, installed per-user at `%LOCALAPPDATA%\Programs\Python\Python313` from the signed python.org installer (no PATH, file-association or launcher changes) | `env_check` |
| Virtual environment | `camera_validation/.venv` | `env_check` (`in_virtualenv: true`) |
| DepthAI | 3.11.0 (commit `e9ead6536e1bf9842d91211fcf80f0b4ef119954`) | `env_check` |
| OpenCV | `opencv-python` 4.14.0.94 (`cv2.__version__` reports 4.14.0) | `pip freeze`, `env_check` |
| NumPy | 2.4.6 | `env_check` |

`winget install` failed on this machine with error `0x8a15000f` ("Data required by the source is missing"). Python was therefore installed from the same official python.org installer that the winget package uses. Its Authenticode signature (Python Software Foundation) was verified before running it. `winget` was not repaired or reset.

---

## 2. Camera A: OAK-D Pro PoE AF

Intended mounting: robot wrist (provisional).

| Item | Value |
|---|---|
| IP address | `169.254.1.222` |
| Device ID | `19443010B14C872F00` |
| MAC address | `44-A9-2C-32-3C-AC` *(user-reported, 4 Nov: ping plus Windows neighbour entry with Camera A alone; no transcript saved)* |
| Product name | `OAK-D-PRO-POE-AF` (device name reports `OAK-D-PRO-POE`) |
| EEPROM board | NG9097, rev R4M2E4 |
| Platform | RVC2 |
| Bootloader | 0.0.26 |
| CAM_A | IMX378 colour, 4056 × 3040, autofocus: yes |
| CAM_B / CAM_C (stereo left/right) | OV9282 monochrome, 1280 × 800 native, no autofocus |
| IR driver present | LM3644 (dot projector / flood). Not commanded on; no pipeline was started. |
| Calibrated sockets | CAM_A, CAM_B, CAM_C |
| Stereo baseline | calibrated **7.508779525756836 cm** (spec 7.500000476837158 cm) |
| Factory vs user calibration | identical (`user_matches_factory: true`) |
| Direct DepthAI connection (`--ip`) | successful, 8.56 s to connect |
| Broadcast discovery | successful: found 1 device in 0.53 s, state `X_LINK_BOOTLOADER` |
| Ping | 4/4 replies, average 1.0 ms, max 2 ms |
| TCP 11490 (XLink) | open |

## 3. Camera B: OAK-D Pro W PoE

Intended mounting: overview tripod (provisional).

| Item | Value |
|---|---|
| IP address | `169.254.1.223` |
| Device ID | `194430108183F12E00` |
| MAC address | `44-A9-2C-37-BA-5D` *(user-reported, as for Camera A; matches the MAC in Camera B's crash-dump log, where the firmware labels it a substitute for an invalid configured MAC)* |
| Product name | `OAK-D-PRO-W-POE` |
| EEPROM board | NG9097, rev R4M2E4 |
| Platform | RVC2 |
| Bootloader | 0.0.28 |
| CAM_A | IMX378 colour, 4056 × 3040, autofocus: no |
| CAM_B / CAM_C (stereo left/right) | OV9282 monochrome, 1280 × 800 native, no autofocus |
| IR driver present | LM3644. Not commanded on; no pipeline was started. |
| Calibrated sockets | CAM_A, CAM_B, CAM_C |
| Stereo baseline | calibrated **7.480551242828369 cm** (spec 7.499999523162842 cm) |
| Factory vs user calibration | identical (`user_matches_factory: true`) |
| Direct DepthAI connection (`--ip`) | successful, 7.99 s to connect |
| Broadcast discovery | successful: found 1 device in 0.52 s, state `X_LINK_BOOTLOADER` |
| Ping / TCP 11490 | 4 Nov: 4/4 replies, average 1.3 ms, max 2 ms; TCP 11490 open (with both cameras attached, so §6.4 applies to which device answered) |

Both cameras report the same sensor set. DepthAI does not report field of view, so the wide-angle optics of Camera B are not visible in these results. The difference is expected to show up in Stage E (calibration intrinsics) and Stage F (imagery).

---

## 4. Discovery observations (3 November)

- Each camera was tested **individually**, not at the same time. The broadcast runs each found exactly one device. Simultaneous discovery (`--simultaneous`, or broadcast with both cameras attached) has **not** been run, and the script's `--simultaneous` mode is untested.
- Both devices responded to DepthAI 3.11.0 over the isolated network.
- The cameras have distinct IP addresses (`.222` and `.223`). However, at one point on 4 November the laptop's ARP cache mapped **both** IPs to Camera B's MAC (§6.4). Later checks showed the correct, distinct MACs (§6.7).
- One failed run is recorded: `discover_20261103_183318` reports `--ip 169.254.1.222` → `RuntimeError: Cannot find any device with given deviceInfo` after 10.5 s. It falls between the Camera A and Camera B sessions, so Camera A was probably disconnected at the time. This has not been confirmed.
- **No camera firmware, bootloader setting, IP configuration or calibration was modified.** Connecting loads the DepthAI runtime into device RAM for the session only. Calibration was only read, and copies were saved on the laptop.
- Luxonis recommends bootloader **0.0.29** for better PoE discoverability. It was **not applied**. The cameras currently run 0.0.26 (A) and 0.0.28 (B).
- No stereo image acquisition has been performed. No image-quality, timing or rectification results exist.

## 5. University networking constraint

- The laptop **appears** to disconnect university Wi-Fi when the wired Ethernet link becomes active. A request for IT assistance is being prepared/submitted.
- **4 Nov, likely cause found (read-only registry check, not confirmed by IT):** a machine Group Policy is set at `HKLM\SOFTWARE\Policies\Microsoft\Windows\WcmSvc\GroupPolicy`:
  - `fMinimizeConnections = 3`, which in Microsoft's documented values for "Minimize the number of simultaneous connections" means "Prevent Wi-Fi when on Ethernet".
  - `fBlockNonDomain = 1`.

  This looks like intended IT configuration rather than a fault, and is worth quoting in the IT request. For camera work it is helpful: only `Ethernet 4` is active during tests, which rules out the Wi-Fi/Ethernet duplicate-discovery problem described in Luxonis's PoE guide.
- Supporting observation: during the camera runs, `Ethernet 4` was the only adapter reported as Up, and the discovery scripts saw only `169.254.80.246`. However, `Get-NetIPAddress` still listed the Wi-Fi address `10.12.58.66` (see `net_check_20261103_182418.txt`). This shows the symptom; it does not show the cause.
- Development workaround: prepare code and dependencies over Wi-Fi, then switch to the isolated Ethernet camera network and run tests locally in PowerShell. Results are written to `results/` for review after reconnecting.
- **No university networking policy, firewall, adapter, routing or antivirus setting was modified.**

---

## 6. 4 November update: both cameras on the switch

The investigation was read-only: no camera connection was opened, and no device, network or policy setting was changed.

### 6.1 Verified runs

Every run was a separate process opening **one** camera by IP. `--simultaneous` has still **not** been run. What is established is "Camera A fails while Camera B is attached", not a failure of two open connections. Which cameras were attached for each run is *(user-reported)*, except at 14:06:26, where broadcast discovery confirms both.

| Time | Command | Result | Stage reached |
|---|---|---|---|
| 14:05:51 | `net_check -CameraIp .222` | ping 4/4, avg 1.3 ms; TCP 11490 open | n/a |
| 14:06:11 | `net_check -CameraIp .223` | ping 4/4, avg 1.3 ms; TCP 11490 open | n/a |
| 14:06:26 | `--broadcast --no-connect` | both found in 0.55 s: `.222` → `19443010B14C872F00`, `.223` → `194430108183F12E00`, both `X_LINK_BOOTLOADER` | discovery OK |
| 14:06:42 | `--ip .222` | **FAILED**: `Cannot find any device with given deviceInfo` after 10.4 s | **search** (no boot) |
| 14:07:04 | `--ip .223` | OK: Camera B, 7.98 s | connected |
| 14:07:27 | `--ip .222` | **FAILED**: same as 14:06:42, 10.4 s | **search** (no boot) |
| 14:10:17 | `--ip .222` | OK: Camera A, 7.98 s *(user: Camera B disconnected)* | connected |
| 14:12:38 | `--ip .222` | **FAILED**: `Failed to find device after booting, error message: X_LINK_DEVICE_NOT_FOUND` after 18.6 s | **boot / re-identification** |
| 14:13:17 | `--ip .223` | OK: Camera B, 8.01 s; DepthAI saved a crash dump at 14:13:26 | connected |

Each successful connection reported the same identity, bootloader, sensors, baseline and user = factory calibration as on 3 November. Broadcast discovery never failed. Camera B never failed.

### 6.2 Crash dump (read, not modified)

- **File:** `%LOCALAPPDATA%\depthai\cache\crashdumps\4a62e2b290e16f4d3f36b0b4df9490a16aea7229\crash_dump_2026-11-04_14_13_26.tar.gz` (6,990 B). Its SHA-256 was `d6bbfa4d…77719` before and after reading. It was read in memory, not extracted.
- **Metadata:**
  - device `194430108183F12E00` (**Camera B**), DepthAI 3.11.0, RVC2.
  - `depthaiBootloaderVersion: 0.0.29` is the bootloader *bundled with the library*, not the camera's (Camera B reports 0.0.28).
- **Crash reports:** two, both `errorId 9001` with no assert or trap information. Uptime was 19.17 s. The meaning of 9001 is not documented in what was read *[verify]*.
- **Device log:**
  - Firmware booted and set **only** static `169.254.1.223/16`.
  - It logged `Overriden invalid mac address, mac: 44:A9:2C:37:BA:5D`.
  - It then logged `initial keepalive, countdown: 7` … `1`, interleaved with **38** `Received device discovery request, sending back - mxid: 194430108183F12E00, state: 1` (booted).
  - Watchdog: initial delay 15,000 ms, timeout 4,000 ms.
- **Interpretation [inferred]:**
  - Camera B was running DepthAI firmware that **no host ever connected to**. It answered discovery as a booted device until the initial-keepalive watchdog expired.
  - The only run that booted a camera without connecting to it is **14:12:38, which targeted Camera A's IP**. So that run most likely booted **Camera B**. The host then searched for its booted device at `.222`, and Camera B's replies came from `.223`, so they were rejected (`X_LINK_DEVICE_NOT_FOUND`).
  - The dump was collected when Camera B was next connected (14:13:17).

### 6.3 `discover_cameras.py` review

This describes the version used for all 4 November runs. Line numbers refer to that version. The verified mode added afterwards is described in §6.8.

- **Identity check is IP-only (line 269).** `--ip` builds `dai.DeviceInfo(ip)` with an empty device ID and state `X_LINK_ANY_STATE`. XLink then sends one unicast discovery to that IP and accepts a reply whose **source IP** matches; the device ID is never checked. This is the XLink `master` source, not verified against the copy bundled with 3.11.0. If frames for `.222` reach another camera, nothing stops the wrong camera being booted. This is an amplifier, not the root cause: Camera A connects normally when it is alone.
- **The `--broadcast --ip` combination is safer, but not selective.** Lines 263–265 reuse the broadcast `DeviceInfo`, which carries the device ID and `X_LINK_BOOTLOADER` state, but the script then connects to *every* discovered camera. There is no option to select one camera by device ID.
- **A device ID can't be passed via `--ip`.** `is_isolated_address()` (line 73, called at line 267) raises `ValueError` for a string that isn't an IP.
- **Cleanup is correct for the host.** `with device:` (line 294) and `ExitStack` (line 282) close sessions. A failed boot leaves the **remote** camera running firmware until its watchdog expires (about 19 s here), and nothing on the host can release it.
- **DepthAI's own console output is not captured** in `results/`, including its crash-dump notice. The script writes nothing to any device.

### 6.4 Host network (read-only, after reconnecting to Wi-Fi)

- **ARP cache (`Get-NetNeighbor`, Ethernet 4, state Stale):**
  - `169.254.1.222 → 44-A9-2C-37-BA-5D`
  - `169.254.1.223 → 44-A9-2C-37-BA-5D`
  - **Both camera IPs resolve to one MAC**, the MAC Camera B's firmware substituted for its invalid configured one. Ping and TCP 11490 checks therefore cannot show *which* camera answered.
- **Routing:**
  - `169.254.0.0/16` is routed only via `Ethernet 4` (metric 5).
  - `Find-NetRoute` selects `Ethernet 4`, source `169.254.80.246`, for both camera IPs.
  - During the tests the scripts saw only `169.254.80.246`.
  - Wi-Fi Direct and Bluetooth adapters hold only tentative `169.254` addresses and are disconnected.
- **Firewall:** all profiles enabled; not modified. Discovery replies and XLink TCP worked, so it is not implicated.
- **PoE switch:** model and power budget not recorded *(needed)*.

### 6.5 Ranked possible causes

| # | Cause | Evidence for | Evidence against / gaps | Assessment |
|---|---|---|---|---|
| 1 | **Transient address-resolution conflict.** At some point before 14:13, the laptop resolved `.222` to Camera B's MAC, so traffic for Camera A reached Camera B. | Both IPs mapped to B's MAC. B's dump shows B booted by a `.222`-targeted run. A failed only with B attached; B never failed. Broadcast discovery (which doesn't depend on unicast delivery) found both. | *Revised later on 4 Nov (§6.7):* **duplicate MAC is refuted**, because Camera A's MAC is `44-A9-2C-32-3C-AC`. Afterwards Windows showed distinct mappings and both cameras connected. How `.222` came to resolve to B's MAC is **unknown**: candidates are switch MAC learning or port behaviour, a transient at camera power-up, or the Windows neighbour cache. | **Most likely explanation of the failures; mechanism unknown; not confirmed** |
| 2 | **IP-only device selection** in the script's `--ip` mode (line 269 of the version reviewed in §6.3; the `--expect` mode in §6.8 addresses it) | XLink matches the reply's source IP only; the device ID is never checked. | Cannot cause the failure alone: A works when alone. | **Contributing**: turns a conflict into booting the wrong camera |
| 3 | **Bootloader age** (A 0.0.26, B 0.0.28; Luxonis recommends 0.0.29 for PoE discoverability) | Could govern MAC fallback and discovery behaviour | No direct evidence; cannot be tested without an update, which is not permitted | Possible underlying factor |
| 4 | **Stranded booted device / retry timing** | After the 14:12:38 failed boot, B stayed in firmware about 19 s; retries inside that window meet a booted, not bootloader, device. | Explains the crash dump, not the first failures (14:06:42) | Secondary |
| 5 | **Multi-interface routing / duplicate discovery** (Luxonis PoE guide) | Luxonis names it as a cause of `X_LINK_DEVICE_NOT_FOUND` | Group Policy forces Wi-Fi off. One `169.254/16` route. Broadcast found each camera exactly once. Host saw a single address. | Unlikely |
| 6 | **Simultaneous PoE power demand** | Switch budget unknown | Both cameras stayed pingable and in bootloader. Failures happened at the search stage, before any load. B ran firmware for 19 s with a watchdog pattern, not a brownout. | Unlikely; record the switch model to close it |
| 7 | **DepthAI 3.11.0 defect** | None specific | B's crash fits expected watchdog behaviour after a boot with no host | Unlikely |

### 6.6 Ping-and-ARP check

The user ran this check later on 4 November (results in §6.7). Keep it for any recurrence: if a connection to a camera fails or returns the wrong ID, run it **before** any further DepthAI connection.

It needs no DepthAI connection, no boot and no setting change: only ping, which the network check already uses, and reading Windows' ARP cache. Run it on Ethernet and save a transcript:

```powershell
cd C:\Users\a1920234\Documents\Phase2_Interface\camera_validation
Start-Transcript -Path ("results\arp_check_{0:yyyyMMdd_HHmmss}.txt" -f (Get-Date))
# Step 1: Camera A only (unplug B's cable at the switch, wait 30 s)
Test-Connection 169.254.1.222 -Count 4
Get-NetNeighbor -IPAddress 169.254.1.222 | Format-Table IPAddress,LinkLayerAddress,State
# Step 2: Camera B only (unplug A, plug in B, wait 30 s)
Test-Connection 169.254.1.223 -Count 4
Test-Connection 169.254.1.222 -Count 4 -ErrorAction SilentlyContinue
Get-NetNeighbor -IPAddress 169.254.1.222,169.254.1.223 | Format-Table IPAddress,LinkLayerAddress,State
# Step 3: both attached (wait 30 s)
Test-Connection 169.254.1.222 -Count 4; Test-Connection 169.254.1.223 -Count 4
Get-NetNeighbor -IPAddress 169.254.1.222,169.254.1.223 | Format-Table IPAddress,LinkLayerAddress,State
Stop-Transcript
.venv\Scripts\python.exe discover_cameras.py --broadcast --no-connect
```

**Interpretation:**

| Observation | Conclusion |
|---|---|
| Step 1 shows `.222` at `44-A9-2C-37-BA-5D` | **Duplicate MAC** on both cameras (cause 1 confirmed) |
| Step 1 shows a different MAC, and in step 2 Camera B replies to `.222` | Camera B also answers for `.222` (IP conflict) |
| Two different MACs throughout, and `.222` never answered by B | The conflict is intermittent; repeat step 3 several times |

With both cameras attached, **use the verified `--expect` mode (§6.8) rather than `--ip`**. `--ip` checks only the IP, so it can boot the wrong camera if the conflict recurs. If a connection attempt fails after booting, wait at least 30 s, or power-cycle the affected camera, before retrying.

Remedies that would need explicit approval, none of them done: giving each camera a unique configured MAC or IP through its bootloader configuration, or updating the bootloader to 0.0.29. Both are device writes. The script-level remedy, selection and verification by device ID, is now in place (§6.8).

### 6.7 Later on 4 November: verified MACs, port swap and sequential success

**MAC addresses** *(user-reported; verified by ping plus Windows neighbour entry with each camera attached alone; no transcript was saved to `results/`)*:

| Camera | IP | MAC | Device ID |
|---|---|---|---|
| A: OAK-D Pro PoE AF | `169.254.1.222` | `44-A9-2C-32-3C-AC` | `19443010B14C872F00` |
| B: OAK-D Pro W PoE | `169.254.1.223` | `44-A9-2C-37-BA-5D` | `194430108183F12E00` |

With both cameras attached, Windows then showed these correct, distinct mappings *(user-reported)*.

**Uncontrolled change:** during troubleshooting, the user **swapped the two cameras' physical switch ports** before the runs below. From the current evidence it is not possible to separate the effect of the port swap from switch MAC relearning, camera power-cycling or changes to the Windows neighbour cache.

**Sequential DepthAI connections with both cameras attached** *(both-attached is user-reported; the logs don't show physical attachment)*:

| Time | Command | Result |
|---|---|---|
| 14:38:28 | `--ip 169.254.1.222` | OK: connected to `19443010B14C872F00` (`OAK-D-PRO-POE-AF`), bootloader 0.0.26, 8.32 s; calibration user = factory; baseline 7.508779525756836 cm |
| 14:40:11 | `--ip 169.254.1.223` | OK: connected to `194430108183F12E00` (`OAK-D-PRO-W-POE`), bootloader 0.0.28, 7.99 s; calibration user = factory; baseline 7.480551242828369 cm |

There is no new crash dump after 14:13:26. The crash-dump folder still holds only `crash_dump_2026-11-04_14_13_26.tar.gz`.

**Status:** sequential connection with both cameras attached has **passed**. Concurrent connection (both open at once) is **not yet tested**. The root cause of the earlier failures is **not confirmed**.

### 6.8 Script changes and prepared concurrent test (run at 14:55, see §6.9)

**Review of the existing `--simultaneous` mode:**
- It selects cameras by IP only, so the wrong camera can be booted and accepted. The connected ID is logged but never checked.
- It runs no pre-check before booting.
- It connects back to back.
- Close errors are not recorded.
- There is no check that both connections stay alive together.
- New crash dumps go unnoticed.
- Its `ExitStack` does close every opened device on exit.

The mode is left unchanged for reference.

**Added to `discover_cameras.py`: verified mode `--expect IP=DEVICE_ID`.**

1. **Argument checks.** Each IP must be link-local, each device ID must be 18 hex characters, and duplicates are refused. The mode cannot be combined with `--ip`, `--broadcast`, `--no-connect` or `--simultaneous`.
2. **Pre-check (boots nothing).** Broadcast discovery runs under the same isolated-network guard as `--broadcast`. Each expected camera must appear **exactly once**, at its IP, with its device ID, in `X_LINK_BOOTLOADER` state. If any expectation fails, **no camera is booted**.
3. **Connect.** Each camera is connected in turn, with a 3 s stagger by default, using the discovered `DeviceInfo`, which carries both the IP and the device ID. According to the XLink source, the search then matches both before booting *(not verified against the copy bundled with 3.11.0)*.
4. **Verify.** After connecting, `getDeviceId()` and the connected IP are compared with the expectation. A mismatch is recorded as `identity_mismatch` and that connection is **closed immediately**. This is the guaranteed backstop, but it runs after boot: if the pre-boot match were not honoured, the wrong camera could still be briefly booted before being rejected.
5. **Hold.** Only if every camera verified, all connections are held open together for `--hold-seconds` (default 5 s). Each one is polled once per second with `isClosed()` and a chip-temperature read. No pipeline is started, so the IR stays off.
6. **Close.** Every opened device is closed in a `finally` block, in reverse order, even if another camera failed, an error occurred or Ctrl+C was pressed. Each close result is recorded.
7. **Record.** For each camera the report holds the requested IP and ID, the actual ID and IP, the status, the connect time, whether it closed cleanly, and all errors. It also lists any **new DepthAI crash dumps**, which count as a failure in this mode.
8. **Result.** The log ends with `RESULT: PASS` (exit code 0) only if every camera reaches `verified_and_held` and closes cleanly.

The `--ip`, `--broadcast` and `--simultaneous` modes are moved into their own function but otherwise unchanged. The one other change: a non-IP string passed to `--ip` no longer crashes the safety check.

**Offline verification (4 Nov, no network or cameras):** the script compiles. A stub-DepthAI logic test passed all eight cases:
- normal pass
- `.222` reporting B's ID
- Camera A still booted
- Camera A missing
- wrong camera after boot
- Camera A connect failure
- Camera B dropping during the hold
- a close that raises an error

In every failure case nothing was booted, or all opened devices were closed. The argument checks refused all five invalid inputs tried. The stub cannot show how real DepthAI behaves.

**Prepared command, awaiting approval** (both cameras attached, Ethernet only, at least 30 s after the last connection):

```powershell
cd C:\Users\a1920234\Documents\Phase2_Interface\camera_validation
.venv\Scripts\python.exe discover_cameras.py --expect 169.254.1.222=19443010B14C872F00 --expect 169.254.1.223=194430108183F12E00 --hold-seconds 10
```

**Expected behaviour on a pass** (about 35 s in total):
1. The pre-check lists both cameras in `X_LINK_BOOTLOADER`.
2. Camera A verifies in about 8 s, followed by a 3 s pause.
3. Camera B verifies in about 8 s.
4. The script logs "Holding 2 verified connection(s) open together for 10 s".
5. Both connections close, each summary shows `status: verified_and_held` and `closed cleanly: True`, and the log ends `RESULT: PASS`.

After the run, the cameras return to bootloader state (wait about 30 s before the next run).

**On failure:** the log ends `RESULT: FAIL` and the report names the camera, its stage (`preflight_failed`, `connect_failed`, `identity_mismatch`, `failed_during_hold`) and the error. If the pre-check fails, nothing was booted. Do not retry immediately: run the §6.6 ARP check first and keep the report.

### 6.9 Stage B concurrent connection passed (14:55)

Command: `discover_cameras.py --expect 169.254.1.222=19443010B14C872F00 --expect 169.254.1.223=194430108183F12E00 --hold-seconds 10`. Report: [discover_20261104_145527.json](results/discover_20261104_145527.json), [.log](results/discover_20261104_145527.log).

| | Camera A | Camera B |
|---|---|---|
| Pre-check (broadcast) | `169.254.1.222` = `19443010B14C872F00`, `X_LINK_BOOTLOADER` | `169.254.1.223` = `194430108183F12E00`, `X_LINK_BOOTLOADER` |
| Connected and verified | `19443010B14C872F00` at `169.254.1.222` (`OAK-D-PRO-POE-AF`), 7.70 s | `194430108183F12E00` at `169.254.1.223` (`OAK-D-PRO-W-POE`), 7.62 s |
| Concurrent hold | 10 s, 10/10 liveness polls; chip 43.4–44.2 °C | 10 s, 10/10 liveness polls; chip 42.1–42.6 °C |
| Status / closed cleanly | `verified_and_held` / True | `verified_and_held` / True |
| Errors | none | none |

Overall: `RESULT: PASS`, two verified connections open at the same time, no new crash dump. The host saw only `169.254.80.246`.

**What this does and doesn't show.** Both cameras can be identified, booted and held open together from one host. It involved no video pipeline: image streaming from two cameras at once, and its bandwidth, are untested.

**History kept.** The earlier failures (§6.1–6.5) happened while Windows resolved `.222` to Camera B's MAC. The cause of that mapping remains **unknown**. It cleared after the switch-port swap and the other uncontrolled changes in §6.7. If it recurs, `--expect` mode will refuse or reject the wrong camera instead of silently using it.

---

## 7. Stage C: stereo capture tool, runs and fix (4 November; historical record, results in §7.5 and §7.8)

### 7.1 API findings (DepthAI 3.11.0, inspected offline)

- **Native mono modes** (from the 14:38 discovery report): CAM_B and CAM_C are OV9282, native 1280 × 800. Their MONO modes are:
  - 1280 × 800 at 1.69–129.6 fps
  - 1280 × 720 at 1.69–143.1 fps, a **separate sensor mode**, not the native frame
  - 640 × 400 at up to 255.7 fps

  So 1280 × 800 at 20 fps is supported.
- **APIs used:**
  - `node.Camera.build(socket, sensorResolution, sensorFps)`
  - `requestOutput(size, type, resizeMode, fps, enableUndistortion)`
  - `node.Sync`: `setSyncThreshold`, `setTimestampSource` (`DEVICE`), `inputs[...]`
  - `MessageGroup["left"]`
  - `MessageQueue.get(timeout)`, which returns `None` on timeout
  - `Pipeline(device)`
  - `Device.setIrLaserDotProjectorIntensity` / `setIrFloodLightIntensity` (both return `bool`)
- **Safety-critical: automatic calibration.** `Pipeline.getAutoCalibrationMode()` defaults to **`ON_START`**. Luxonis documents that this runs stereo calibration when a 1280 × 800 or 640 × 400 stereo pipeline starts, and, if it validates, **flashes the result as user calibration**. The factory calibration is not touched. It has been the default since DepthAI 3.6. ([AutoCalibration](https://docs.luxonis.com/software-v3/depthai/depthai-components/host_nodes/auto_calibration), [Dynamic Calibration](https://docs.luxonis.com/hardware/platform/depth/dynamic-calibration))
  - Setting `DEPTHAI_AUTOCALIBRATION=OFF` did **not** change the getter in an offline check.
  - `pipeline.setAutoCalibrationMode(OFF)` did.
  - The Stage A/B scripts never start a pipeline, so they could not trigger it, and every saved calibration copy so far shows user = factory.
- **Network features avoided:** `RemoteConnection` and holistic record/replay are not used. Nothing listens on a host port.

### 7.2 `capture_stereo.py`

1. **Select (Stage B method).** The broadcast pre-check runs under the isolated-network guard. The camera must be seen once at its IP, with its ID, in bootloader state. After connecting, the ID and IP are checked, and a mismatch closes the device and stops the run.
2. **Pre-start checks.** All of these must pass before anything streams:
   - CAM_B and CAM_C are OV9282 and offer a native MONO mode of the requested size and fps.
   - The calibration is read and hashed, and a copy is saved.
   - IR dot projector and flood light are set to 0 and acknowledged.
   - `AutoCalibrationMode` is set to `OFF` and the getter confirms it.
3. **Pipeline.**
   - CAM_B (left) and CAM_C (right): `Camera` nodes at 1280 × 800 and 20 fps, GRAY8 output at the native size, `enableUndistortion=False`. No resize, crop, rectification or depth.
   - Pairing: a `Sync` node on device timestamps, with the threshold at half the frame period (25 ms at 20 fps), so frame *n* can never be paired with *n*±1.
   - Host queue: maxSize 8, non-blocking.
   - IR is set to 0 again after start.
4. **Acquire.** By default it collects 200 pairs, with a 60 s cap and a 5 s no-frame timeout. It stops at the first frame of unexpected size. With `--preview`, a local window shows a half-scale side-by-side view (q or Esc stops).
5. **Record** to `results/stereo_<timestamp>_<deviceId>/`:
   - `pairs.csv`, one row per pair: group/left/right sequence numbers, device and host timestamps, L–R difference, width, height, type, exposure and ISO
   - `report.json`: configuration, sensor modes, IR and auto-calibration results, measured fps (device and host), |L–R| statistics (mean/median/p95/max), equal-sequence count, sequence gaps, stop reason, errors, new crash dumps, calibration before/after hash
   - `calibration_before_run.json`
   - `capture.log`
   - `images/`: 5 representative pairs (after 20 warm-up pairs), each saved as native left PNG, native right PNG and an unscaled 2560 × 800 side-by-side PNG
6. **Shutdown.** In a `finally` block, whether the run ended normally, on timeout, on error, on Ctrl+C or on a refusal: stop the pipeline, re-read and compare the calibration, then close the device. `RESULT: PASS` requires all of: the target pairs reached, no errors, pipeline stopped, device closed, calibration unchanged, and no new crash dump.

It imports only `discover_cameras` (unchanged), DepthAI, OpenCV and NumPy.

### 7.3 Offline validation (no network, no cameras)

- The tool compiles.
- A stub-DepthAI test passed all **11** cases:
  1. normal run (30 pairs, 9 PNGs, 2560 × 800 side-by-side, 20 fps, sequence statistics)
  2. frame timeout
  3. XLink error mid-stream
  4. Ctrl+C (exit code 130)
  5. auto-calibration stuck ON (pipeline never started)
  6. IR not acknowledged (never started)
  7. unsupported mode (never started)
  8. wrong camera (never started)
  9. calibration changed (FAIL)
  10. wrong frame size (stops at the first frame)
  11. dropped pairs counted

  In every case the pipeline was stopped if it had started, and the device was closed.
- Argument validation refused 8 invalid inputs before importing DepthAI, and created no output folders.
- **Not exercised offline:** the real DepthAI pipeline, real Sync behaviour and the `--preview` window.

### 7.4 Prepared first capture (Camera A) (historical: run at 15:22, see §7.5)

```powershell
cd C:\Users\a1920234\Documents\Phase2_Interface\camera_validation
.venv\Scripts\python.exe capture_stereo.py --expect 169.254.1.222=19443010B14C872F00 --preview
```

On Ethernet only. Camera B may stay attached; only Camera A is opened. Wait at least 30 s after any previous connection. Point the camera at a static, textured, ordinarily lit scene. Expected run time is about 25 s: pre-check under 1 s, connect about 8 s, pipeline start a few seconds, then 200 pairs at 20 fps in about 10 s. Pressing q stops early, saves the data so far, and reports `FAIL` (incomplete).

### 7.5 First captures on Camera A (4 Nov, 15:22 and 15:23): recorded as FAIL

Both runs are preserved unmodified with their original `RESULT: FAIL`:
- [stereo_20261104_152236_19443010B14C872F00](results/stereo_20261104_152236_19443010B14C872F00/report.json)
- [stereo_20261104_152331_19443010B14C872F00](results/stereo_20261104_152331_19443010B14C872F00/report.json)

| | Run 1 (15:22:36) | Run 2 (15:23:31) |
|---|---|---|
| Selection | `19443010B14C872F00` at `.222`, pre-check `X_LINK_BOOTLOADER`, 7.68 s | same, 7.65 s |
| IR off acknowledged (before / after start) | True / True | True / True |
| AutoCalibrationMode | `OFF` (confirmed) | `OFF` (confirmed) |
| Pairs / stop reason | 200 / `target_pairs_reached` | 200 / `target_pairs_reached` |
| Delivered size and type | 1280 × 800 both, GRAY8 | 1280 × 800 both, GRAY8 |
| fps (device timestamps / host arrival) | 19.80 / 20.00 | 20.00 / 20.22 |
| \|L–R\| timestamp difference, ms (mean / median / p95 / max) | 0.015 / 0.015 / 0.017 / 0.024 | 0.014 / 0.014 / 0.016 / 0.021 |
| Pairs with equal L/R sequence number | 200/200 | 200/200 |
| Frame gaps | **1 gap after pair 79: sequence 79 → 82, 2 frames missing, 150 ms interval** (not shown in the terminal summary) | none; every interval 50.0 ms |
| Auto-exposure settling | exposure above 20 ms until pair 26 (max 30 ms, ISO up to 1549) | until pair 14 |
| New crash dump | none | none |
| **Failure** | `calibration re-read failed: RuntimeError: Device already closed or disconnected: not connected` | same |

Measurement notes:
- The left/right differences are a first look at timing only. Stage D still needs at least 1,000 pairs and analysis of the gaps.
- Whether run 1's missing frames were dropped by the sensor, the `Sync` node or the host queue cannot be told apart from these records.

**Image check.**
- All 30 saved PNGs are 800 × 1280 uint8, with no duplicate frames.
- The pair-20 images were taken before auto-exposure settled: 6.9% (run 1) and 19.1% (run 2) of the left image is saturated, against about 0.06% later.
- Visual check of run 2, pair 110: native-looking frames, and near objects sit further right in the left (CAM_B) image than in the right (CAM_C) image, which is the expected sign for a correctly ordered pair. This is a visual check only.

**Cause of the failure.** DepthAI 3.11.0's `PipelineImpl::stop()` closes every device in the pipeline (`device->close()`; the destructor does the same, per the depthai-core source). `capture_stereo.py` called `pipeline.stop()` and then tried to re-read calibration from the same, now closed, device. The `device closed: True` in those reports came from that state, not from a successful verification step. This was a defect in the verification sequence, not a camera fault. Two further defects were found in the same review:
- The `group_seq` metric was invalid, because the `Sync` group's sequence number was always 0.
- An exception in a post-run step could have escaped the `finally` block.

**Calibration from saved evidence.** All saved copies of Camera A's calibration are **identical by content** (SHA-256 `e69cdb49…`):
- November 3 user and factory (18:24)
- November 4 user and factory (14:10, 14:38)
- the before-run reads of both captures

So **run 1 did not change the calibration**: run 2's start-of-run read equals the November 3 baseline. The state **after run 2 is not established** by any saved evidence.

### 7.6 Fix (historical: validated offline, then confirmed on hardware at 15:37–15:40, see §7.8)

- **New `calibration_check.py`:**
  - Compares calibrations by their **parsed content**, listing the JSON paths that differ; hashes are only recorded.
  - Provides a read-only reconnection: it waits up to 60 s for the camera to return to `X_LINK_BOOTLOADER`, connects with the Stage B verified selection, reads **user and factory** calibration, and **always closes**.
  - Creates no pipeline, so automatic calibration cannot run.
  - It can also be run on its own to compare against saved baselines.
- **`capture_stereo.py` shutdown order:**
  1. Re-read user and factory calibration **while still connected** (in-session check).
  2. `pipeline.stop()`, which closes the device; `device_closed_by_pipeline_stop` is recorded.
  3. Explicit close if the device is still open.
  4. Write `pairs.csv` and the measurements.
  5. If the pipeline ran: **post-run read-only reconnection**, compared with the start-of-run data and with the optional `--baseline-user` / `--baseline-factory` files.

  `calibration_unchanged` is True only if every check ran and matched. It is None, and the run fails, if any check could not be completed.
- **Unchanged:** the auto-calibration OFF check, the IR-off acknowledgements (before and after start), the native-mode check, the Sync configuration and the verified selection.
- **Also changed:**
  - Frame gaps are now listed in the report and log, with frame-interval statistics.
  - `group_seq` is removed.
  - Warm-up before saving images is increased to 40 pairs.
  - The factory calibration is also saved at the start of the run.
- **Offline validation:** all **20** stub checks passed. The stub reproduces "stop() closes the device" and the delayed return to bootloader state. The cases are:
  - normal run with in-session and post-run verification
  - disconnection mid-capture
  - camera never back in bootloader (reconnection fails)
  - reconnection read fails
  - reconnection to the wrong camera
  - calibration changed in session
  - calibration changed after stop
  - baseline mismatch
  - no baselines given
  - post-run discovery raising
  - frame timeout, XLink error and Ctrl+C
  - auto-calibration stuck, IR not acknowledged, unsupported mode and wrong camera
  - wrong frame size
  - dropped frames visible
  - standalone read
  - the difference listing itself

  In every case all opened devices were closed. Argument validation of both tools refused bad inputs before importing DepthAI.

### 7.7 Proposed next steps (historical: run at 15:37–15:40, see §7.8)

Both on Ethernet only, at least 30 s after any previous connection.

1. **Independent read-only calibration check.** No pipeline, no streaming. It establishes Camera A's current state after run 2:

   ```powershell
   cd C:\Users\a1920234\Documents\Phase2_Interface\camera_validation
   .venv\Scripts\python.exe calibration_check.py --expect 169.254.1.222=19443010B14C872F00 --baseline-user results\calibration_user_19443010B14C872F00_20261103_182445.json --baseline-factory results\calibration_factory_19443010B14C872F00_20261103_182445.json
   ```

   It passes if the current user and factory calibration equal the 3 November copies. Output goes to `results\calibration_check_<timestamp>_19443010B14C872F00\`.
2. **Final Camera A capture retest:**

   ```powershell
   .venv\Scripts\python.exe capture_stereo.py --expect 169.254.1.222=19443010B14C872F00 --preview --baseline-user results\calibration_user_19443010B14C872F00_20261103_182445.json --baseline-factory results\calibration_factory_19443010B14C872F00_20261103_182445.json
   ```

   Expected run time is about 45–60 s: about 25 s of capture as before, then a wait for the camera to return to bootloader state, then an approximately 8 s read-only reconnection. On a pass:
   - the log shows `Calibration: in-session equal True | post-run (read_ok) equal True, baselines [... True, ... True] | unchanged: True`;
   - it shows `Device closed: True (by pipeline.stop: True) | post-run device closed: True`;
   - it ends `RESULT: PASS`.

### 7.8 Stage C initial functional validation: complete for both cameras (4 Nov)

| | Camera A (OAK-D Pro PoE AF) | Camera B (OAK-D Pro W PoE) |
|---|---|---|
| Read-only calibration check | [calibration_check_20261104_153712](results/calibration_check_20261104_153712_19443010B14C872F00/report.json): user = factory = 3 Nov baselines, `PASS` | [calibration_check_20261104_154017](results/calibration_check_20261104_154017_194430108183F12E00/report.json): user = factory = 3 Nov baselines, `PASS` |
| Capture | [stereo_20261104_153749](results/stereo_20261104_153749_19443010B14C872F00/report.json) | [stereo_20261104_154034](results/stereo_20261104_154034_194430108183F12E00/report.json) |
| Pairs, size, type | 200, 1280 × 800 both, GRAY8 | 200, 1280 × 800 both, GRAY8 |
| \|L–R\| ms (median / p95 / max) | 0.015 / 0.016 / 0.022 | 0.015 / 0.017 / 0.021 |
| Equal L/R sequence numbers | 200/200 | 200/200 |
| Calibration | in-session, post-run reconnection and both baselines equal | same |
| Shutdown | closed by `pipeline.stop`; post-run device closed | same |
| Result | `PASS` | `PASS` |
| **Continuity** | **6 frames missing** (after pair 59, 350 ms interval); 19.41 fps | none missing; 20.00 fps, every interval 50.0 ms |

**Capturing 200 pairs is not the same as capturing 200 consecutive pairs.** Across all four Stage C runs, every one delivered 200 correctly paired frames at native size, and every lost frame was lost from *both* sensors together. But only two runs were continuous:

| Run | Camera | Delivered pairs | Missing sensor frames | Largest delivery stall | Result as recorded |
|---|---|---|---|---|---|
| 15:22 | A | 200 | 2 (after pair 79) | 480 ms (pair 72) | FAIL (verification defect, §7.5) |
| 15:23 | A | 200 | 0 | 96 ms | FAIL (verification defect, §7.5) |
| 15:37 | A | 200 | 6 (after pair 59) | 683 ms (pair 52) | PASS |
| 15:40 | B | 200 | 0 | 92 ms | PASS |

With one Camera B run against three Camera A runs, these runs **do not show that Camera A is more lossy**: the order, the switch port and the time all differed.

### 7.9 Frame-loss analysis (from saved evidence)

**What the timing shows.** In both lossy runs:
1. A **delivery stall** came first (480 ms and 683 ms): relative latency rose by the same amount.
2. The backlog then drained **faster than real time**, at 23–33 ms per pair, consistent with a bandwidth-limited burst of about 2 MB per pair.
3. The gap appeared only **after 7–8 backlogged pairs** had arrived, and latency fell by roughly the duration of the missing frames.

The number of missing frames matches stall length minus about 8 frames of buffering: 683 ms ≈ 13.7 periods, giving about 6 lost; 480 ms ≈ 9.6 periods, giving about 2 lost. Runs whose largest stall was under 100 ms lost nothing.

**Interpretation, not verified.** The host queue (8 deep, non-blocking) discards its *oldest* messages. Here the oldest frames were kept and the *newest* were lost. That fits a loss **upstream of the host queue**: frames dropped on the camera while delivery to the laptop was stalled (camera frame pools; `Sync` inputs 10 deep, non-blocking). A loss in the host queue would put the gap straight after the stall. The cause of the stalls is unknown. Candidates are the network path (USB Ethernet adapter, dock, switch, TCP retransmission) or the host. Nothing measured so far separates them.

**Where frames can be dropped, delayed or discarded** in the Stage C implementation:
1. Camera frame pools on the device (size not recorded).
2. `Sync` input queues on the device (10, non-blocking). Unmatched frames are discarded with their partner, which hides losses on one sensor alone.
3. XLink/TCP over the USB Ethernet adapter and switch (about 328 Mbit/s of raw GRAY8 per camera).
4. The host queue (8, non-blocking, oldest discarded).
5. The Python loop. The preview ran on every frame (resize, colour conversion, `imshow`, `waitKey`). PNGs were written synchronously for 5 pairs (3 files each, one of them 2.5 MB). Both add host processing time, and neither was measured.

The Stage C records could not see host-queue fill, capture-to-receipt latency, host processing time, per-sensor losses or network retransmissions. The `Sync` group sequence number was always 0, so it cannot be used.

---

## 8. Stage D: frame-continuity validation (historical record of the preparation; run at 16:00–16:25, results in §9)

### 8.1 Changes to `capture_stereo.py`

All Stage B/C protections are kept: device-ID verification, auto-calibration OFF enforcement, IR-off acknowledgements, native-mode check, and in-session plus post-run calibration comparison by content.

- **Per-pair measurements** (in `pairs.csv`):
  - `latency_ms`: host receipt (`dai.Clock.now()`) minus the host-synchronised capture timestamp
  - `wait_ms`: time blocked waiting for the pair
  - `loop_busy_ms`: host processing time for the pair (preview, copying)
  - `left_queue_size` / `right_queue_size`: host queue fill just after each read
- **Gap analysis.** For each gap, the report records the largest preceding delivery stall, the latency before and after, and the host queue fill before it. It labels the pattern as one of three:
  - host queue full (overflow on the laptop)
  - delayed, then lost upstream
  - lost upstream with no backlog

  The label is an interpretation, worded "consistent with".
- **Continuity block, separate from `RESULT`:** `consecutive`, expected frames, missing frames, gaps, losses per 1,000 frames, and losses per sensor (in `host-seq` mode). The log prints a `CONTINUITY:` line.
- **`--pairing host-seq` diagnostic.** Raw left and right queues are paired on the host by equal sequence number, then checked against the device timestamps (within half a period). It counts losses on each sensor separately, unpaired frames and timestamp mismatches, which the `Sync` node hides.
- **Buffering and network:**
  - `--queue-size` sets the host queue (default 8, as in Stage C).
  - The camera frame-pool sizes and the `Sync` input settings are recorded.
  - `--network-stats` records read-only Windows counters before and after: `netstat -s -n -p tcp` (retransmissions; `-n` because without it netstat hangs) and `Get-NetAdapterStatistics` for `Ethernet 4` (bytes, discards, errors), with timeouts. The report includes the delta and the receive throughput.
- **Overhead:**
  - PNGs are copied in memory during capture and **written after streaming**.
  - Process CPU use during acquisition is recorded.
  - Nothing is logged per frame.
  - The preview stays optional, and its cost appears in `loop_busy_ms`.
- **Misc:** `--label` is added to the output folder name. Run length is checked against `--max-seconds`.

**Offline validation:** all 27 stub checks passed. The Stage C cases were kept, plus:
- a gap after an upstream delay (classified "upstream")
- a gap after a full host queue (classified "host queue full")
- `host-seq` normal pairing
- a loss on the left sensor only (per-sensor: left 1, right 0; right frame unpaired)
- a timestamp mismatch
- network-counter arithmetic (328 Mbit/s computed)
- deferred PNG writing, including after Ctrl+C
- one real read-only `network_snapshot` call (2.0 s)

The tests found and fixed: `netstat` hanging without `-n`; a `KeyError` on the wrong-frame-size path.

**Unintended run (15:56:03).** During argument checks, `--pairs 1200` was accepted as valid input and the script ran on Wi-Fi. It was refused by the isolated-network guard **before any discovery or connection** (folder `stereo_20261104_155603_19443010B14C872F00`: `safety_abort`, no broadcast results). No camera was contacted.

### 8.2 Procedure (historical: approved and run as D1–D7, see §9)

**Fairness controls:**
- Both cameras stay attached throughout. Record which switch port each uses.
- Same static, textured scene and lighting for both.
- Laptop on mains power. No other applications. Ethernet only.
- Cameras **interleaved** (A, B, A, B), so drift over time doesn't favour one.
- Identical settings for both: 1280 × 800, 20 fps, 1,200 pairs (60 s), 3 PNGs written after streaming, **no preview**, `--network-stats`.
- Wait at least 30 s between runs.

| Run | Camera | Mode | Purpose |
|---|---|---|---|
| D1 | A | device-sync | baseline continuity |
| D2 | B | device-sync | baseline continuity |
| D3 | A | device-sync | repeat |
| D4 | B | device-sync | repeat |
| D5 | A | host-seq | losses per sensor; Sync-node losses |
| D6 | B | host-seq | same |
| D7 | A | device-sync + `--preview` | preview overhead (compare `loop_busy_ms` and continuity with D1/D3) |

Each run takes about 1.5–2 minutes, so about 15 minutes in total. A run's `RESULT` is functional; **continuity is the Stage D measurement and is not a pass criterion**. Depending on the results, possible follow-ups:
- `--queue-size 32`: does host buffering matter?
- swapping the two cameras' switch ports: is a loss tied to the camera or to the port?
- repeats to reach at least 3 per camera and mode.

**How the results will be read:**
- Losses per 1,000 frames, per camera and mode.
- Whether each gap follows a stall and a latency rise (upstream) or a full host queue (laptop side).
- `host-seq` per-sensor losses: one sensor alone means sensor or transport per stream; both together means delivery.
- TCP retransmissions and adapter discards during runs that had gaps.
- Receive throughput, about 328 Mbit/s expected per camera.

### 8.3 Simultaneous video acquisition (later, not implemented)

Two cameras at 1280 × 800 × 2 × 20 fps GRAY8 need about **655 Mbit/s** of raw payload through one 1 Gbit/s USB Ethernet adapter. That is close to the adapter's practical limit, and single-camera stalls already occur. Simultaneous streaming should only be attempted after Stage D shows where single-camera losses arise. It would then use one process with two verified devices (Stage B `--expect`), per-camera continuity and latency, and adapter throughput. Expect to need lower fps, encoding on the camera (later streaming milestone) or a second network adapter.

---

## 9. Stage D results: D1–D7 (4 Nov, 16:00–16:25)

All figures below are recomputed from each run's `report.json` and `pairs.csv`. Every run: 1,200 pairs at 1280 × 800, `RESULT: PASS`, calibration unchanged (in-session, post-run and both baselines), clean shutdown, no new crash dump. The original folders are unmodified.

### 9.1 Results

| Run | Missing frames | fps (device) | Stalls > 100 ms (longest) | Latency ms median / p95 / max | Host queue max | Processing ms mean / max | CPU % | Laptop TCP retransmits |
|---|---|---|---|---|---|---|---|---|
| D1 A sync | **9** (1 gap) | 19.85 | 4 (684.7) | 47.5 / 70.7 / 838 | 0 | 0.14 / 1.3 | 4.7 | 5 |
| D2 B sync | 0 | 20.00 | 1 (102.6) | 47.5 / 60.0 / 150 | 0 | 0.16 / 1.6 | 5.9 | 6 |
| D3 A sync | 0 | 20.00 | 1 (102.6) | 47.6 / 68.0 / 153 | 0 | 0.14 / 0.9 | 4.2 | 5 |
| D4 B sync | **4** (1 gap) | 19.93 | 2 (568.1) | 47.6 / 69.7 / 565 | 0 | 0.15 / 1.5 | 5.2 | 9 |
| D5 A host-seq | 0 (per sensor 0/0) | 20.00 | 4 (331.5) | 39.7 / 61.1 / 321 | 0 / 0 | 0.14 / 1.3 | 7.8 | 4 |
| D6 B host-seq | 0 (per sensor 0/0) | 20.00 | 3 (303.0) | 38.5 / 52.4 / 289 | 0 / 0 | 0.14 / 1.3 | 7.6 | 6 |
| D7 A sync + preview | 0 | 20.00 | 4 (336.4) | 47.4 / 82.3 / 333 | 0 | **6.05** / 87.1 | **33.9** | 11 |

Every pair in every run had equal left/right sequence numbers, with |L–R| at most 0.030 ms. Adapter receive and send discards and errors were 0 in every run. Receive throughput was 356–362 Mbit/s, against 328 Mbit/s of raw GRAY8 payload.

### 9.2 Findings from the records (evidence)

1. **Frame losses: 2 of 7 runs, one camera each** (D1 Camera A, D4 Camera B), 13 of 8,413 sensor frames in total. Counting Stage C as well, Camera A lost frames in 3 of 7 runs and Camera B in 1 of 4. **This is not a camera-specific fault on the evidence so far.**
2. **Delivery stalls happen in every run.** There were 19 stalls over 100 ms in 7 minutes, about 2.7 per minute, at irregular spacing (0.7–27.6 s apart; no periodicity). Their durations cluster:

   | Duration | Count |
   |---|---|
   | 100–150 ms | 6 |
   | about 165 ms | 1 |
   | **295–336 ms** | **10** |
   | 568 and 685 ms | 2 |

   D1's 685 ms stall followed a 298 ms stall only 5 pairs earlier.
3. **The laptop was never the bottleneck.** The host queue was empty after every one of the 8,400 reads. Processing took at most 1.6 ms per pair without preview. During every stall the queue stayed at 0 while latency rose. So the delay arose **before the laptop's queue**: on the camera, in the transport, or in the laptop's network stack.
4. **Frames were lost only when the backlog exceeded about 6–7 frames.**
   - All 17 loss-free stalls raised latency by at most 286 ms (5.7 frames).
   - The lossy events raised it by 517 ms (D4) and 791 ms (D1).
   - Subtracting the frames lost, the backlog absorbed was 6.3 and 6.8 frames. The two Stage C events give about 6.6 and 6.7.
5. **The gap is the stall, recorded late.**
   - The missing frames were *captured during* the stall: 246–646 ms into D1's 684 ms stall, and 403–553 ms into D4's 568 ms stall.
   - The gap appears 8 pairs (229–252 ms of host time) after the stall ends, because the buffered frames are delivered first, in a 21–33 ms-per-pair burst.
   - The sensors kept capturing throughout: sequence numbers, assigned at capture, carry on across the gap, and device timestamps are exactly 50.0 ms apart everywhere else.
6. **Laptop TCP counters don't explain it.** Laptop retransmissions were 4–11 per run, including loss-free runs. They count only the **laptop's own** retransmissions, so they cannot show retransmissions by the camera on the video stream. Stage D's `--network-stats` was blind to that direction; the label has now been corrected.
7. **Read-only settings.** The USB adapter exposes no flow-control, energy-efficient-Ethernet or interrupt-moderation settings, and receive segment coalescing is off. The minimum TCP retransmission timeout is not readable without admin rights.

### 9.3 Clock check (latency definition)

`latency_ms` = `dai.Clock.now()` at receipt minus `ImgFrame.getTimestamp()`. The second is the device capture time mapped by DepthAI onto the host clock.
- **The mapping is stable.** `getTimestamp − getTimestampDevice` jitters by 0.07–1.1 ms and drifts by at most 2.6 ms over 60 s.
- **The clocks share a base.** `dai.Clock.now()` minus Python's monotonic clock has a standard deviation of 0.13–0.20 ms.
- **The minimum latency is plausible:** 34–46 ms, never negative.

The clocks are compatible, and **changes** in latency are reliable to about ±1–2 ms. The **absolute** value carries an unknown constant: which point in the exposure `getTimestamp()` refers to is not documented in what was read, and exposure was about 8–10 ms. So absolute latency is uncertain by up to one exposure time.

### 9.4 device-sync versus host-seq

- **Continuity:** host-seq 0 of 2 lossy runs, device-sync 2 of 5. **Not evidence of greater robustness.** host-seq's largest stall raised latency by 281 ms, below the observed loss threshold, so neither host-seq run met a stall large enough to test it.
- **Latency:** host-seq is about 8–9 ms lower (median 38.5–39.7 against 47.4–47.6 ms). *Hypothesis:* device-sync waits for both frames on the camera and sends one 2 MB message, while host-seq sends two 1 MB streams in parallel.
- **Stall counts** were similar (host-seq 4 and 3; device-sync 1–4). **CPU** was higher in host-seq (7.6–7.8% against 4.2–5.9%), from 1 ms polling. The host queues were empty in both modes.
- **Per-sensor losses:**
  - host-seq tracks each sensor's sequence separately; this was proven offline, but no single-sensor loss happened on hardware, so it is untested there.
  - Every per-sensor sequence was continuous.
  - host-seq is a **different camera-side pipeline** (no `Sync` node, two XLink streams), not a passive observer of device-sync.
- **D5's "pending left 1" was stale bookkeeping.** D5 received 1,200 left and 1,200 right frames, formed 1,200 pairs, and its last pair was 1199/1199. The count was written at the end of the previous loop pass, before the final right frame arrived. **Fixed:** the count is now written when the source closes. Per-sensor receipt times (`left_rx_clock_s`, `right_rx_clock_s`) are now also recorded, so a future run can show whether both streams stall together. Both changes passed the offline suite (all checks, including new assertions).

### 9.5 Preview overhead (D7)

- **Can establish:** for one camera at 20 fps on this laptop, the preview cost:
  - mean 6.05 ms per pair (median 4.65, p95 15.3);
  - a one-off 87.1 ms at pair 0, when the window was created; after that the maximum was about 20 ms;
  - CPU 34% of one core, against 4–8% without preview.

  That is within the 50 ms frame budget, and it never backed up the host queue (always 0). Processing just before each of D7's four roughly 300 ms stalls was 3.6–12.6 ms, so **the preview did not cause those stalls**.
- **Cannot establish:**
  - whether the preview changes how often stalls or losses happen (one run; stalls are random);
  - what the viewer actually saw, or the display latency (`imshow` and `waitKey` give no display timing);
  - behaviour with two cameras, in Unity or on the Quest, or under other laptop loads.

### 9.6 Candidate explanations: evidence versus hypothesis

| Candidate | Status |
|---|---|
| Laptop host queue or Python loop | **Ruled out for these runs** (queue always 0; processing ≤ 1.6 ms, or ≤ 20 ms with preview after the first frame) |
| `Sync` node as the source of loss | **Not supported.** Losses always hit both sensors together and only after a delivery stall. Its inputs are 10 deep, non-blocking. It may still be part of the buffering chain. |
| Camera-side buffering as the *loss* site | **Consistent with the evidence, not verified.** The capacity of about 6–7 frames is constant across 4 events. The recorded pools are 3 raw and 3 ISP frames per camera node (the output-pool getter returned none). *Hypothesis:* frames held for transmission exhaust the camera's buffers, so new frames are dropped. |
| Origin of the *stalls* | **Located only as "between the camera's output and the laptop's queue"**: the camera's XLink/TCP sending, the switch or cable, the USB Ethernet adapter or dock, or the Windows network stack. Not distinguishable with current data. |
| TCP retransmission timeouts | **Hypothesis.** The cluster at 295–336 ms is similar to common minimum TCP retransmission timeouts. A single lost packet on a TCP stream holds up the whole stream until it is re-sent (head-of-line blocking). The camera is the sender for the video; its boot log shows a BSD-style network stack (`net.inet.tcp.delayed_ack`). Its timer values are unknown. Testing this needs a packet capture. |
| Bandwidth saturation | **Not supported for one camera:** 356–362 Mbit/s, steady, about 36% of the link. It becomes relevant for two cameras (about 720 Mbit/s). |
| Laptop adapter errors or power saving | **No evidence** (0 discards or errors; no periodicity), but **not excluded**. |

### 9.7 Implications for the remote supervision interface

- **Freezes on the local link alone, per camera stream:**
  - freezes of 100 ms or more about 2.7 times per minute;
  - roughly 300 ms freezes about 1.4 times per minute;
  - longer freezes (568–685 ms, with frame loss) twice in 7 minutes;
  - image age up to about 0.84 s.

  Any wide-area link will add its own.
- **What a naive display does:** it holds the last frame during a freeze, then plays the backlog in a burst (frames 21–33 ms apart). That is a visible stutter, and the image is stale at the moment of decision.
- **For Allow, Inspect and Intervene decisions:**
  - A decision made during a freeze is based on imagery up to about 0.8 s old.
  - Measured response times relative to robot events would include a random extra delay that differs between trials, and between the 2D and XR conditions, unless the age of the displayed frame is known.
- **Design consequences** (for the gateway and the Unity receivers; none implemented):
  1. Carry capture timestamps and sequence numbers from end to end (the protocol v2 fields already proposed in the Task 02 audit).
  2. Log the age of each displayed frame, and freeze events, alongside participant decisions.
  3. Display the latest frame and drop stale backlog after a stall, which bounds image age.
  4. Use the same transport for both conditions, so freezes affect both alike.
  5. Show staleness on the experimenter interface.
  6. Whether participants see any staleness indicator is an **experimental-design decision for the researcher** (transparency versus confound).
- **For the gateway's transport:** a TCP-based link turns one lost packet into a whole-stream freeze. Keep this in mind when choosing the transport in Task 04.

### 9.8 Recommended next diagnostics (smallest first; none implemented, all need approval)

1. **No action on the host queue.** It was never used, so enlarging it cannot help (evidence).
2. **Passive continuity logging continues** in every later capture. The tool already does this, so more data accumulates at no extra cost.
3. **Swap the switch ports** of Camera A and Camera B, then one run each (physical change only). This separates camera from port, cheaply.
4. **Decisive network test: a packet capture during one 60 s run**, using Windows' built-in `pktmon` or Wireshark. It would show whether the roughly 300 ms stalls coincide with camera retransmissions. It is read-only, but needs administrator rights and possibly IT approval, so it is the researcher's decision.
5. **Camera buffer experiment, only if lossless recording matters.** Raise the camera's frame pools or the `Sync` input queues (pipeline settings, not persistent), to see whether the 6–7 frame threshold moves. Trade-off: it turns losses into longer catch-up bursts, which is worse for a live display.
6. **Not recommended now:**
   - changing Windows TCP or adapter settings (policy, and no evidence yet);
   - lowering fps as a "fix" (it changes the stimulus);
   - repeating trials without new instrumentation (7 runs already show the pattern; rates need far more runs).

### 9.9 Can Stage E proceed independently?

**Yes.** Rectification and stereo-geometry checks use static scenes and individual synchronised pairs. A missing or delayed frame does not affect the geometry of the frames that do arrive, and every delivered pair was correctly matched (equal sequence numbers, |L–R| ≤ 0.03 ms). Conditions for Stage E:
1. Reuse the capture safeguards, especially **auto-calibration OFF**. A `StereoDepth` pipeline is exactly the case auto-calibration targets.
2. **Use a low frame rate, for example 5 fps.** Raw plus rectified left/right is 4 streams, and at 20 fps that would be about 655 Mbit/s for one camera. At 5 fps it is about 164 Mbit/s.
3. Keep logging continuity passively.

Network troubleshooting can be deferred to the streaming milestone (Task 04), where the transport is designed anyway. The researcher decides on the packet capture (§9.8 item 4).

---

## 10. Stage E preparation: rectification and geometric validation (historical record; run as E1–E5, results in §11)

### 10.1 Calibration and API review (offline)

**Saved user calibration:** the device rectifies with the user calibration, which equals the factory calibration for both cameras.

| | Camera A (OAK-D Pro PoE AF) | Camera B (OAK-D Pro W PoE) |
|---|---|---|
| Model | perspective, 14 coefficients (OpenCV rational + thin prism + tilt) | same |
| fx / fy (px, 1280 × 800) | 799.5 / 799.3 (L), 801.7 / 801.3 (R) | 565.4 / 565.2 (L), 566.4 / 566.3 (R) |
| Principal point (L / R) | (645.3, 378.4) / (630.5, 384.4) | (645.0, 386.6) / (651.4, 386.7) |
| Raw horizontal FOV, pinhole / distortion-aware / spec | 77.4° / 77.3° / 80° (L), 72° (R) | 97.1° / **129.1°** / 127° |
| Raw vertical FOV (distortion-aware) | 52.5° | 81.1° |
| Baseline (calibrated) | 7.509 cm | 7.481 cm |
| T left → right (cm) | (−7.508, 0.030, −0.088) | (−7.479, 0.022, −0.124) |
| Stored rectification rotations vs OpenCV `stereoRectify` | 0.008° / 0.010° | 0.003° / 0.006° |
| `stereoEnableDistortionCorrection` | true | true |

- **The coefficient ordering is confirmed.** Camera B's distortion-aware FOV (129.1°) matches its specification (127°), so DepthAI's 14 coefficients follow OpenCV's ordering.
- **The stored rectification is consistent with the extrinsics.** The rotations stored in the calibration agree with OpenCV's rectification of the same calibration to within 0.01°.
- **DepthAI 3.11.0 rectification controls:** `StereoDepth` provides `syncedLeft/Right` (the raw frames it rectified) and `rectifiedLeft/Right`, plus `setRectification`, `setRectifyEdgeFillColor`, `setAlphaScaling` (0 = only valid pixels; 1 = all source pixels kept), `enableDistortionCorrection` and `setRectificationUseSpecTranslation`.
- **Default distortion handling depends on lens FOV.** `useHomographyRectification` defaults to "AUTO": a mesh with distortion correction for FOV over 85°, otherwise a plain 3×3 homography with **no distortion correction**. With Camera A's 77° pinhole FOV, the default would probably differ between the two cameras. Stage E therefore sets distortion correction explicitly, by default `on` for both, so the processing rule is the same. `auto` is available for one comparison run.

### 10.2 Offline preview on saved Stage D raw pairs (host rectification with OpenCV, alpha 0 and 1)

Folders: `stage_e_offline_20261104_164156_A_D3` and `stage_e_offline_20261104_164200_B_D2`, holding `geometry_offline.json` and guide-line comparisons. These are **host** rectifications; the device may use a different rectified camera matrix, which the live tool measures.

| | Camera A (D3 scene) | Camera B (D2 scene) |
|---|---|---|
| alpha 0: valid area / FOV H × V | 100% / 75.2° × 51.4° | 100% / **103.4° × 76.6°** (from 129° × 81° raw) |
| alpha 1: border / inscribed-rectangle FOV | 5.1% / 76.5° × 52.3° | **47.6%** / 129.1° × 81.0° |
| Raw vertical disparity \|dy\| | covered region only: median 9.2 px | median 3.5–3.9 px, p95 8.0–9.6 px |
| Rectified (alpha 0) \|dy\| | **insufficient**: 218–279 reliable matches, but in only 4 of 9 regions (plain wall, a very near object occluding the right view). Covered region only: median 0.43–0.45 px, p95 0.9–1.1 px | **median 0.74–0.79 px, p95 1.59–1.65 px** (5 / 11 arcmin), max 3–6 px; signed median −0.75 px (a small consistent offset) |

Reading these results:
- The calibration appears to rectify both cameras to **sub-pixel median, roughly 1.6 px p95** residual vertical disparity, but only on natural scenes, and Camera A's result is only partial.
- For the wide camera, the alpha choice is a **framing trade-off**. Alpha 0 crops horizontally from 129° to 103°; alpha 1 keeps the whole field but leaves half the frame black. Intermediate values, and what the device does by default, are to be measured live.
- Camera A needs a scene with texture across the whole field before a whole-image score is possible.
- *Data note:* the saved Stage C/D images include an identifiable person. Stage E scenes should contain no people.

### 10.3 Tools (validated offline)

- **`stereo_geometry.py`** (host analysis, no camera access):
  - calibration summary (intrinsics, distortion, extrinsics, baseline, stored rotations, pinhole and distortion-aware FOV)
  - host rectification for given alphas, with valid area, inscribed valid rectangle and effective FOV
  - **vertical disparity** from SIFT matches: ratio test 0.75, mutual check, MAGSAC epipolar check (1.5 px), disparity in [−2, 0.5 × width]
  - Scoring rule: a score requires **at least 50 reliable matches spread over at least 5 of 9 regions**; otherwise the result is `insufficient`. Statistics for a covered region only are labelled explicitly as not a whole-image score.
  - It reports median, p95, max and mean in px and arcmin, centre against periphery, signed median and the fraction over 1 px.
  - **Fit of the rectified camera matrix** the device actually used, from raw ↔ rectified matches of the same frame, with the fit residual.
  - Guide-line comparisons (thin neutral lines; **analysis aid only, never for participants**).
  - An offline mode that applies a saved calibration to saved raw pairs.
- **`rectify_stereo.py`** (live tool, not yet run):
  - **Safeguards**, all shared with Stage C: verified device-ID selection, native-mode check, IR off acknowledged before and after start, `AutoCalibrationMode.OFF` confirmed before start (a `StereoDepth` pipeline is exactly what automatic calibration targets), and calibration compared by content in-session, after a read-only reconnection and against the 3 November baselines.
  - **Pipeline:** CAM_B / CAM_C native 1280 × 800 GRAY8, no undistortion, at **5 fps** (four streams, about 164 Mbit/s). It feeds `StereoDepth` with rectification on, distortion correction explicit (`on` by default), border fill 0 and alpha optional. Depth and disparity are not used or sent.
  - **Grouping:** a group is formed **only when all four streams carry the same sequence number**, and the device timestamps of raw and rectified are recorded. Per-stream continuity, unmatched and pending frames are reported.
  - **Defaults:** 45 groups, 30 warm-up groups (6 s, for auto-exposure), 5 saved groups. Each saved group has 4 native PNGs and a comparison image.
  - **After shutdown, the geometry analysis records:**
    - raw and rectified vertical disparity
    - the device's rectified camera matrix per eye, with fit residual
    - valid area and black-border fraction predicted from that matrix, checked against the zero-valued pixels actually present
    - inscribed rectangle, and effective FOV for the full output, the central row/column and the inscribed rectangle
  - **Outputs:** `report.json`, `groups.csv`, `geometry.json`, `rectify.log` and `images/` in `results/rectify_<timestamp>_<deviceId>_<label>/`. `RESULT` is functional (capture, safety, calibration); `GEOMETRY` is reported separately.
- **Offline validation:** all **18** stub checks passed. The stub served real Camera B frames as synced raw and their host-rectified versions as rectified.
  - Fitted rectified fx 503.88 against the 503.84 applied; residual median 0.18 px.
  - Valid area 100%; rectified \|dy\| median 0.76 px against 3.9 px raw; all 3 groups scored.
  - Explicit alpha and distortion off; `auto` leaves the setting untouched.
  - A dropped rectified frame is detected per stream, and that group is not formed.
  - Sequence numbers that never match give a clean timeout.
  - Auto-calibration stuck ON and IR not acknowledged are both refused before start.
  - Calibration changed after stop gives FAIL.
  - Ctrl+C, a wrong raw size and an analysis failure are each recorded (an analysis failure does not mask the functional result).
  - 4 invalid argument sets were refused.

  The Stage C/D `capture_stereo` suite still passes. **Not exercised offline:** real `StereoDepth` behaviour, its default alpha, whether its outputs carry the input sequence numbers and timestamps (if not, grouping times out and the run fails safely), and the device's mesh rectification.

### 10.4 Live procedure (historical: approved and run as E1–E5, see §11)

**Scene, per camera:**
- Static, ordinary indoor lighting, no people in view, IR off.
- Texture across the **whole** field, including corners: posters, printed text or patterns, a bookshelf.
- A **near** textured object and a **far** one:
  - Camera A: about 0.3–0.5 m and 1.5–3 m (wrist working range)
  - Camera B: about 0.8–1 m and 3–5 m
- Straight **vertical and horizontal** edges (door frame, shelf).
- A **ruler or printed checkerboard** if available.
- Camera stationary on a stable support. Ethernet only. At least 30 s after any previous connection.

| Run | Camera | Settings | Purpose |
|---|---|---|---|
| E1 | A | distortion correction on, alpha unset | device default framing with explicit correction |
| E2 | B | same | same |
| E3 | A | `--alpha 0` | crop to valid pixels |
| E4 | B | `--alpha 0` | wide-angle crop (expected about 103° horizontally) |
| E5 | A | `--distortion-correction auto` | DepthAI's own default (probably homography, no distortion correction) |

Each run takes about 1–1.5 minutes: 9 s of streaming, connection, post-run verification and analysis. Intermediate alpha values for Camera B can follow once E2 and E4 are reviewed.

### 10.5 Considerations for Quest 3 presentation

- **Measured by the tools:**
  - residual vertical disparity in px and arcmin at the camera, over the whole field and for centre against periphery
  - black borders and cropping
  - effective FOV
  - consistency between raw and rectified frames
- **Not decided by the tools:**
  - **Comfort depends on the display mapping**: quad size and distance in the headset, and the angular magnification from camera to eye. It may need a short viewing check by the researcher.
  - The camera baseline (7.5 cm) is wider than a typical adult interpupillary distance (about 6.3 cm). Disparities are therefore larger than natural viewing at the same distance (hyperstereo, about 1.2×), which matters most for near objects at the wrist camera.
- **Framing rules, a researcher decision:** whatever crop or alpha is chosen should also apply to the **2D condition**, which shows the same rectified left image, so framing and FOV stay matched. For Camera B the choice trades construction-relevant peripheral view against black borders.
- **No interface overlays:** none of the guide lines, overlays or indicators produced here are intended for the participant interface.
- **Limits of static-scene results:**
  - They test geometry at one moment, under one lighting, at the scene's depths.
  - They do not cover temperature drift, vibration on the robot wrist, camera motion (rolling or global shutter effects are not tested here), or residual errors in textureless regions where no matches exist.
  - A median vertical disparity says little about individual image regions; the periphery is reported separately for this reason.

---

## 11. Stage E results: E1–E5 (4 Nov, 17:03–17:10) — hardware tests complete, configuration provisional

These results come from offline analysis of the saved runs, using `geometry.json` and the saved images. The re-analysis script is `analyse_stage_e.py`, and its output is in [stage_e_analysis_20261104_171558](results/stage_e_analysis_20261104_171558/analysis.json). The original folders are unmodified.

### 11.1 Functional results

- **All 5 runs:** `PASS` with 45/45 groups.
  - Raw and rectified timestamps are identical (0 ms).
  - No gaps, unmatched or pending frames; |L–R| ≤ 0.021 ms.
  - Calibration unchanged in-session, after the read-only reconnection and against both 3 November baselines.
  - Every device closed; no new crash dump.
- **The camera was not moved** between the runs of the same camera: raw images agree to a median of 0.11–0.23 px across runs. The comparisons between runs therefore isolate the rectification setting.
- **Scene limits:**
  - No run produced reliable matches in the **bottom third** of the image (the table surface), so that region is unverified.
  - Near objects (disparity over 100 px) were sparsely sampled.
  - The scene again contained an identifiable person (data-handling note).

### 11.2 On-device rectification against the calibration

The rectified camera matrix was fitted per eye from raw ↔ rectified matches of the same frame. In every run both eyes share the same matrix (cx and cy equal to within 0.01 px), and the calibration's distortion model plus stored rotations reproduce the device output to a **median residual of 0.05–0.24 px**.

| Run | fx / fy (px) | Pixel aspect | Centre resolution (px/°) | Full-frame FOV H × V | Black border L / R (measured) | Common border-free crop | Usable FOV |
|---|---|---|---|---|---|---|---|
| E1 A default | 798.9 / 798.3 | 1.00 | 13.9 | 77.4° × 53.2° | 1.19% / 4.34% | 1238 × 770 (x 39–1276, y 6–775) | **75.5° × 51.5°** |
| E3 A alpha 0 | 810.6 / 809.1 | 1.00 | 14.1 | 76.6° × 52.6° | 0.06% / 2.85% | 1250 × 781 | 75.3° × 51.5° |
| E5 A auto | 798.9 / 798.3 | 1.00 | 13.9 | 77.4° × 53.2° | 1.19% / 4.34% | 1238 × 770 | 75.5° × 51.5° |
| E2 B default | 565.0 / 564.7 | 1.00 | 9.9 | 97.1° × 70.6° | 0% / 0% | full frame | **97.1° × 70.6°** |
| E4 B alpha 0 | **317.9 / 465.4** | **1.46** | **5.6 × 8.1** | 127.2° × 81.3° | 0.01% / 0.05% | 1280 × 793 | 127.2° × 80.8° |

The raw (distortion-aware) FOV is 77.3° × 52.5° for Camera A and 129.1° × 81.1° for Camera B.

**How the defaults compare with OpenCV:**
- DepthAI's **default alpha keeps the raw central scale**: the rectified fx is about equal to the raw fx (798.9 against 799.5; 565.0 against 565.4).
- DepthAI's **alpha differs from OpenCV's.** For Camera B at alpha 0, OpenCV's `stereoRectify` (offline preview, §10.2) chose a square fx of 503.8, giving 103° × 77°. DepthAI chose a non-square 317.9 / 465.4 that keeps nearly the full raw field. The offline preview therefore does not predict the device's alpha behaviour.

### 11.3 Camera A: AUTO against explicit distortion correction ON

**No material difference** in DepthAI 3.11.0 with this calibration:
- **Images:** mapping E1 → E5 rectified, feature to feature, gives an affine scale of 1.0001 / 0.9999 and a displacement median of 0.22 px (max 0.99 px). That is the same as the scene's own raw-to-raw agreement (0.23 px).
- **Fitted matrices and areas:** identical to within 0.01 px, with identical black borders (1.19% / 4.34%) and identical FOV.
- **Distortion was corrected in both.** A plain homography fits raw → rectified with p95 residual 5.0 px (E5) and 6.6 px (E1). The calibrated distortion model fits with 0.29 px and 0.27 px. Without correction, Camera A's distortion would shift its corners by 4.5–12.2 px (edge midpoints 1.4–5.8 px).

*Inference:* AUTO probably follows the calibration's `stereoEnableDistortionCorrection: true` rather than the 85° FOV rule. This is not verified in the source. Explicit `on` remains the recommended setting, because it does not depend on that heuristic or on future library changes.

### 11.4 Default framing against alpha 0

- **Camera A:** alpha 0 (E3) is a uniform **1.4–1.5% enlargement** of E1 (affine scale 1.0146 / 1.0135), which removes about 10 px at the edges.
  - It does **not** make both eyes border-free: the right eye keeps 2.85% black along its left and bottom edges.
  - The common usable field is the same (75.3° against 75.5°).
  - So alpha 0 gives Camera A no benefit.
- **Camera B:** the two settings are a genuine trade-off.

  | | Default (E2) | Alpha 0 (E4) |
  |---|---|---|
  | Pixels | square | non-square: E4 is E2 scaled by **0.563 horizontally and 0.825 vertically** (measured directly between the images) |
  | Centre resolution | 9.9 px/° | 5.6 × 8.1 px/° (**−44% horizontally**, −18% vertically) |
  | Field kept | 97.1° × 70.6° (raw 129° × 81°) | 127° × 81° |
  | Lost or distorted | about 16° on each side and about 5° top and bottom | a rectilinear projection over 127° **strongly stretches content near the edges** |
  | Visible in comparison images | — | peripheral objects (near bottle, ceiling vent, right-hand monitors) that E2 omits, with visible horizontal squeeze |

### 11.5 Residual vertical misalignment

Model fitted per group: dy = offset + b·x + c·y + d·disparity (x and y normalised to ±1).

| | Camera A (E1 / E3 / E5) | Camera B (E2 / E4) |
|---|---|---|
| \|dy\| median / p95 / max (px) | 0.46–0.55 / 0.95–1.21 / 1.75–8.09 | 0.95–1.11 / 1.92–2.28 / 3.16–7.79 |
| Median in arcmin at the camera | about 2.1 | about 6.7 (E2), about 7.0 (E4) |
| Constant offset | +0.2 to +0.8 px | **−0.64 to −0.96 px** |
| Left-to-right term b (px per half width) | ≈ 0 | **+0.6 to +1.2** (dy about −1.6 px at the left edge to about −0.2 px at the right) |
| Vertical-scale term c | +0.2 to +0.6 | +0.3 to +0.6 |
| Depth term d | ≈ 0 | ≈ 0 |
| Residual after the model, median / p95 | 0.18–0.21 / 0.86–1.01 px | 0.20–0.22 / 1.17–1.36 px |
| Grid pattern | flat (+0.3 to +0.6 px) | largest in the **upper-left** (−1.5 to −1.7 px median), near 0 on the right |

- **Camera B's offset is geometric, not a matching artefact.** Its pattern is the same in angular terms in both framings, and it does not depend on depth. It corresponds to a residual relative rotation between the rectified eyes: pitch about 0.09° and roll about 0.065°. Camera A's is about 0.04° pitch.
- **The likely source is the calibration** rather than DepthAI's rectification, because the stored rotations match the calibration's extrinsics to 0.01° (§10.1). This is not verified.
- **Camera B's upper-left periphery has genuine local errors of −3.0 to −3.6 px** (about 21 arcmin). They recur in several groups and have high patch correlation.

### 11.6 Outlier matches

| Run, value | Location | Evidence | Verdict |
|---|---|---|---|
| E1 **+8.09 px** | (523, 462), disparity 135 px (typical 12–44) | patch NCC 0.43; neighbours +0.64 px; no match there in other groups | **mismatch** |
| E3 +4.87 px | disparity 355 px | NCC 0.26; neighbours +0.79; other groups +0.4–0.6 | **mismatch** |
| E3 +3.52 / +3.34 px | near field, disparity about 185 px | isolated; nearby matches in other groups +0.1–1.0 | probable mismatch (near field otherwise unsampled) |
| E4 **−7.79 px** | (793, 619), disparity 226 px, sparse region | neighbours −0.83 px about 200 px away; no persistence | **probable mismatch**; local geometry in that sparse near-field area is unverified |
| E2 / E4, −3.0 to −3.6 px (about 20 cases) | upper-left, mostly x 190–500, y 5–160 | NCC 0.85–0.98; recur at the same points across groups | **real local misalignment** (§11.5) |

The reported maxima above 4 px are mismatches. They are not evidence of calibration error. Camera B's roughly 3.5 px upper-left values are real.

### 11.7 Consistency between the 2D and XR conditions

- **Same stream and processing.** Both conditions should show the **same rectified left stream with the same crop and scale**. Otherwise field of view, magnification and framing differ between conditions.
- **Camera A's eyes have different borders** (left 1.2%, right 4.3%). The 2D view (left eye only) would show less black edge than XR. Applying the **common crop to both eyes and to 2D** removes this difference.
- **E4-type non-square pixels would make the conditions differ.** A square-pixel 2D monitor would show a squeezed image unless it were re-stretched, and the XR view would need the same correction on its display surface. This is a mismatch risk to avoid.
- **On-screen size is a separate design decision.** Each condition's angular display size (monitor size and distance against Quest quad size and distance) affects perceived scale and disparity.

### 11.8 Provisional configuration (recommendation; subsequently approved, see §12.1)

| | Camera A (wrist) | Camera B (overview) |
|---|---|---|
| Rectification | ON, **distortion correction explicitly ON** | ON, **distortion correction explicitly ON** |
| Alpha | **unset** (DepthAI default; square pixels, native scale) | **unset** (DepthAI default) |
| Crop | **common border-free crop x 39–1276, y 6–775 (1238 × 770)**, the same for both eyes and for the 2D view | none needed (no borders) |
| Result | 75.5° × 51.5°, 13.9 px/°, square pixels | 97.1° × 70.6°, 9.9 px/°, square pixels |
| Why | alpha 0 adds nothing (same usable FOV, still bordered); the crop removes the eye-specific black edges | keeps central resolution and natural geometry for inspecting gaps and edges; alpha 0's extra 30° costs 44% horizontal resolution, non-square pixels and strong edge stretch |
| Validation needed | confirm the crop on further frames or a second scene (it is fixed by the geometry, so it should not change); headset comfort | confirm that 97° × 71° covers the construction area from the planned tripod position; headset comfort |

**Camera B's residual misalignment** (median about 1 px; up to −3.6 px upper-left) has three options, each needing approval:
1. Accept it, pending the headset check.
2. Apply a fixed host-side vertical shift and roll to one rectified eye (offset about −0.9 px, roll about 0.065°). This would first need validating on a second scene.
3. Recalibrate. That would overwrite the camera's user calibration, so it is not recommended now.

For both cameras: **Quest 3 comfort is unverified**, and the 7.5 cm baseline gives about 1.2× hyperstereo.

### 11.9 Decisions requiring the researcher's approval

*Status at the end of 4 Nov:* items 1–2 are approved (§12.1). Item 1 is still pending the CRATER coverage check. Items 3–4 are in progress: E6–E9 and the pre-specified correction rule (§12.4). Items 5–6 are open.

1. **Camera B framing:** accept 97° × 71° (recommended), or require wider coverage. If wider, reposition the tripod or test other configurations, but not alpha 0.
2. **Camera A crop:** apply the common border-free crop to both eyes and to the 2D view.
3. **Camera B residual misalignment:** accept, apply a host-side correction, or recalibrate later.
4. **Second validation scene (a hardware test):** texture in the lower third, near-field objects and **no people**. It would confirm the crop and the Camera B pattern, and cover the unverified regions.
5. **Headset comfort check:** how and when to view both configurations in Quest 3.
6. **2D presentation:** show the rectified left image with the same crop, and decide the monitor's angular size relative to the Quest display.

**Limits of these results:** one static indoor scene per camera, one lighting level and one session. The bottom third and the near field are unverified. Temperature, vibration and motion are not tested.

---

## 12. Stage E follow-up: approved provisional configuration and second-scene test (prepared, not run)

### 12.1 Approved provisional configuration (researcher, 4 Nov)

| | Camera A (wrist) | Camera B (overview) |
|---|---|---|
| Rectification | distortion correction explicitly ON, default alpha | distortion correction explicitly ON, default alpha; **alpha 0 not used for participants** |
| Crop | **x 39–1276, y 6–775 inclusive** = NumPy `img[6:776, 39:1277]` = 1238 × 770, applied to both eyes and to the 2D view; full rectified images kept for analysis | none |
| FOV | 75.5° × 51.5° | 97.1° × 70.6°, **pending the CRATER coverage check** |

`rectify_stereo.py` defaults are already this configuration: `--distortion-correction on`, alpha unset.

**Crop convention, verified offline.** `stereo_geometry.inscribed_rect` returns inclusive indices. On all 10 saved E1/E5 groups, both eyes have **0 border pixels** inside `img[6:776, 39:1277]`. The crop is also **maximal**: extending any side by one pixel reaches a black border in at least one eye (left or top: the right or left eye respectively; right or bottom: the left or right eye).

### 12.2 Scene-1 baseline (offline, [epipolar_analysis_20261104_scene1_baseline](results/epipolar_analysis_20261104_scene1_baseline/analysis.json))

Robust fit with 95% intervals from a block bootstrap over 5 × 5 cells:

| | Camera B, E2 | Camera A, E1 / E5 |
|---|---|---|
| Offset | **−0.88 px** (95% −1.00 to −0.68) = −5.3 arcmin | +0.43 / +0.53 px (95% from +0.08 to +0.72) = +1.9 / +2.3 arcmin |
| Roll | **+0.057°** | +0.008° / +0.007° |
| Vertical scale | +0.115% | +0.06% / +0.08% |
| Verified 5 × 5 cells (≥ 10 matches) | **11 / 25** | 13 / 25 |
| Lower-third cells verified | **0** | 0 |
| Corners verified | top-left only | top-left and top-right |
| Crop border-free | n/a | yes (both runs) |

Candidate corrections on Camera B, **in-sample only** (fitted and evaluated on E2):

| Candidate | \|dy\| median | p95 |
|---|---|---|
| Shift | 1.10 → 0.27 px | 2.13 → 1.21 |
| Shift + roll | 1.10 → 0.21 px | 2.13 → 1.16 |
| Shift + roll + vertical scale | 1.10 → 0.19 px | 2.13 → 1.09 |

The image-level check (warp the right eye, then re-match) agrees with these to within 0.03 px. In-sample improvement **is not evidence** that a correction generalises; the second scene provides the held-out test.

### 12.3 Tools added (offline only; validated)

- **`analyse_epipolar.py`**, for any saved `rectify_*` runs:
  - fits dy = offset + b·x + c·y + d·disparity per run, robustly (trimmed at 3.5 × MAD), with 95% block-bootstrap intervals, converted to arcmin and degrees using each run's fitted rectified camera matrix
  - a 5 × 5 map of signed dy with match counts, where a cell needs **at least 10 matches to count as verified**; lower-third and corner coverage are reported explicitly
  - dy in near, middle and far disparity bins
  - **cross-scene consistency** per camera with pre-specified tolerances: offset 0.25 px, roll 0.02°, vertical scale 0.05%, or the combined 95% interval if that is larger
  - **candidate corrections** C1 (shift), C2 (shift + roll) and C3 (shift + roll + vertical scale), fitted on chosen runs and evaluated on held-out runs: overall, lower third, corners, upper left and fraction over 1 px, plus an image-level warp and re-match check
  - a crop check for Camera A

  Corrections are evaluated **on saved images only and never applied to a camera stream**. For display, a correction could be split half to each eye to keep the framing symmetric.
- **`coverage_check.py`:**
  - `generate` prints ArUco markers (DICT_4X4_50).
  - `analyse` finds the expected markers in both rectified eyes of a saved run. It reports each marker's angular position (fitted rectified camera matrix) and its margin to the displayed edge (the Camera A crop, if given). The status is "covered with margin", "visible but near the displayed edge" or "missing or intermittent".
  - The markers are a **test aid only** and must be removed before participant sessions.
  - Printable set: [coverage_markers_20261104_173011_140mm](results/coverage_markers_20261104_173011_140mm/README.txt): IDs 0–7, 140 mm black squares, pages 186 × 200 mm (A4 portrait at 100%). All 8 are detected from the files. Sizes that would not fit A4 with at least 10 mm margins are refused.
- **Offline validation:** all **8** checks passed, using synthetic second scenes built from real E2 images in the scratchpad.
  - An unchanged copy is judged consistent with E2, with an offset difference of 0.00 px.
  - **An injected +0.5 px shift and +0.05° roll was recovered as −0.499 px and −0.0505°** (expected −0.500 and −0.050), and the scenes were flagged as inconsistent.
  - The correction fitted on E2 reduced the unchanged copy to a median of 0.21 px. On the injected scene it left 0.41 px, so the held-out test exposes a scene-dependent change. The image-level checks agreed to about 0.02 px.
  - Scene-1 lower-third coverage was correctly reported as 0, i.e. partial.
  - The approved crop passed on E1/E5, and a deliberately wrong crop (x0 = 30) failed.
  - Rendered markers gave all four statuses correctly.

  The tests found and fixed three defects: Windows `C:` paths in `--run`; marker pages too wide for A4; and output-folder name collisions.

### 12.4 Proposed second-scene hardware test (prepared, not run; start with E6, see NEXT SESSION: START HERE)

All runs use the approved configuration, 60 groups at 5 fps, 30 warm-up groups and **10 saved groups**. Camera B is the priority.

| Run | Camera | Scene | Purpose |
|---|---|---|---|
| E6 | B | **mixed depth, full field**: tripod about 1.2–1.5 m high, tilted down so the **lower third sees textured floor or table** (printed patterns, newspaper, a textured mat) at 0.8–1.5 m; textured sheets near **all four corners**; objects at about 1 m, 2–3 m and 4–6 m (back wall) | offset and roll over the whole frame, including the lower third and corners; depth dependence |
| E7 | B | **near, single depth**: a textured wall or bookshelf at about 1.0–1.5 m filling the whole frame (at 1 m the frame covers about 2.3 m × 1.4 m) | dense, uniform coverage at one distance, including the corners |
| E8 | A | **wrist working range, mixed depth**: textured board or table under the lower third at 0.25–0.5 m; objects at about 0.3 m and 0.6 m; textured background at 1.5–3 m; corners textured | crop validity, near-field alignment, lower third |
| E9 | A | **near planar**: a textured poster or printed sheets at about 0.4 m filling the frame (about 0.62 m × 0.39 m at that distance) | near-field alignment throughout the frame |

- **Scene requirements for all runs:** static; ordinary lighting; **no people in view**; the camera on a stable support, not moved during a run; IR off (enforced); Ethernet only; at least 30 s between runs.
- **Record** the distances to the near, middle and far objects (a tape measure is enough) and the tripod height and tilt.
- **Timing:** each run takes about 1.5–2 minutes (12 s of streaming, connection, read-only post-run verification and analysis of 10 groups).

**Decision rule for a Camera B software correction (pre-specified).** Consider applying a correction only if all of these hold:
1. Offset and roll are consistent across scenes 1, 2 and 3.
2. The **held-out** result (fitted on one scene, evaluated on the others) reduces median |dy| by at least 50% and p95 by at least 25%, and makes no verified 5 × 5 cell's p95 worse by more than 0.3 px.
3. The image-level check agrees with the point-level result to within 0.15 px.

If any of these fails, no software correction; recalibration would then be a separate decision. A correction would be implemented in the streaming gateway or receivers, never in the camera or its calibration.

### 12.5 CRATER coverage check for Camera B (separate session; not part of the second-scene test)

1. Print IDs 0–7 at 100% and measure the printed black square (expected 140 mm). Mount the markers flat and facing the camera.
2. Place the markers at the **boundaries of what the overview must show**: 0–3 at the four corners of the construction area; 4 at the robot base; 5 at the block supply; 6–7 at the furthest planned placement positions, or at the top of the tallest planned structure on a stand. The researcher decides the final list.
3. Set up the tripod at its planned position. Record its location, height, tilt and distance to the centre of the area.
4. **No robot motion and no robot software.** The UR20 stays in its safe state, as for any camera-only test.
5. Capture and analyse (commands below). The check passes if every marker is "covered with margin", with at least 2° from the displayed edge in both eyes. If not, adjust the tripod position rather than the rectification.

### 12.6 Exact commands (analysis and CRATER commands current; the E6–E9 capture commands here are superseded by §12.7)

**Second-scene test** (Ethernet only, both cameras attached, at least 30 s between runs):

```powershell
cd C:\Users\a1920234\Documents\Phase2_Interface\camera_validation
$A = "--expect","169.254.1.222=19443010B14C872F00","--baseline-user","results\calibration_user_19443010B14C872F00_20261103_182445.json","--baseline-factory","results\calibration_factory_19443010B14C872F00_20261103_182445.json"
$B = "--expect","169.254.1.223=194430108183F12E00","--baseline-user","results\calibration_user_194430108183F12E00_20261103_183335.json","--baseline-factory","results\calibration_factory_194430108183F12E00_20261103_183335.json"
$S = "--groups","60","--warmup-groups","30","--save-groups","10"
.venv\Scripts\python.exe rectify_stereo.py @B @S --label E6_B_s2_mixed
.venv\Scripts\python.exe rectify_stereo.py @B @S --label E7_B_s2_near
.venv\Scripts\python.exe rectify_stereo.py @A @S --label E8_A_s2_mixed
.venv\Scripts\python.exe rectify_stereo.py @A @S --label E9_A_s2_near
```

**Offline analysis afterwards** (no camera; fitting and evaluating in both directions):

```powershell
.venv\Scripts\python.exe analyse_epipolar.py --run E2_B_default:scene1 --run E6_B_s2_mixed:scene2 --run E7_B_s2_near:scene3 --run E1_A_default:scene1 --run E8_A_s2_mixed:scene2 --run E9_A_s2_near:scene3 --crop 39,6,1276,775 --fit-on E2_B_default --evaluate-on E6_B_s2_mixed,E7_B_s2_near
.venv\Scripts\python.exe analyse_epipolar.py --run E6_B_s2_mixed:scene2 --run E2_B_default:scene1 --run E7_B_s2_near:scene3 --fit-on E6_B_s2_mixed --evaluate-on E2_B_default,E7_B_s2_near
```

The setup-preview versions of these E6–E9 commands, which replace the ones above for the live test, are in §12.7.

**CRATER coverage check** (later, separate approval):

```powershell
.venv\Scripts\python.exe rectify_stereo.py @B --groups 40 --warmup-groups 30 --save-groups 3 --label E10_B_coverage
.venv\Scripts\python.exe coverage_check.py analyse --run E10_B_coverage --expect-ids 0-7 --min-margin-deg 2
```

### 12.7 Setup preview for positioning targets (`rectify_stereo.py --setup-preview`; 38 offline checks passed; **not yet tested with a physical camera or a real OpenCV window**)

**Workflow.** The preview starts only after every pre-start safeguard has passed: verified identity, native mode, IR off acknowledged and auto-calibration OFF confirmed. A local window then shows the **live rectified left/right pair** at half scale (1280 × 444 including the text bar).
- **Text bar:** device ID and IP, run label, measured fps (from device timestamps over the last 10 groups), the current sequence number, and the key instructions.
- **G** toggles a **5 × 5 grid matching `analyse_epipolar.py`**, a texture-point count per cell of the left image (FAST corners: a positioning guide, not the analysis's SIFT matches), and the Camera A crop outline (`--preview-crop`).
- **Space** closes the preview and runs the **unchanged** capture: warm-up, 60 groups, 10 saved groups, logging, in-session and post-run calibration checks, and analysis.
- **Q, Esc or closing the window** cancels: no capture; `RESULT: CANCELLED` (exit code 3). Shutdown and the post-run calibration verification still run, and a cancel with any shutdown or calibration problem is reported as FAIL.
- **Time limit:** the preview cancels itself after `--setup-max-minutes` (default 20).
- **Errors:** Ctrl+C gives `INTERRUPTED` (exit code 130). A disconnection or frame timeout during the preview ends the run as FAIL. Shutdown is clean in every case.

**Integrity**
- The preview reads from the **same four-stream source** as the capture, so rectification, framing and pairing are unchanged.
- Overlays are drawn **only on a scaled display copy**; preview groups are never saved.
- The capture then runs its own warm-up and frame collection.

**On the saved E2 scene the counts read 0–4 in the bottom two rows** and 0–1 on the blank upper-right wall. Those are exactly the cells `analyse_epipolar.py` found unverified. **Aim for clearly non-zero counts (roughly 30 or more) in every cell** before pressing Space. This is a heuristic.

**Offline validation:** all 38 checks passed, 26 behavioural and 12 of argument validation.
- The 11 earlier capture cases are unchanged.
- **Space:** capture passes (12 groups, continuous, calibration unchanged), the preview closes once, and the **saved rectified images are byte-identical to the source frames** (no overlay leaks).
- **Q, uppercase Q, Esc, window closed and time limit:** each gives `CANCELLED` with no capture or images, pipeline stopped, device closed and calibration verified.
- **Disconnection during the preview:** FAIL, all devices closed, preview closed.
- **Frames stopping:** frame timeout.
- **Ctrl+C:** exit code 130, clean.
- **G:** toggles the grid on the display only (frames 1–2 with grid, 3–4 without).
- `preview_image` leaves frame data unchanged.
- **Not exercised offline:** a real OpenCV window and a real camera.

**E6–E9 with the setup preview (replaces the §12.6 capture commands; awaiting approval):**

```powershell
cd C:\Users\a1920234\Documents\Phase2_Interface\camera_validation
$A = "--expect","169.254.1.222=19443010B14C872F00","--baseline-user","results\calibration_user_19443010B14C872F00_20261103_182445.json","--baseline-factory","results\calibration_factory_19443010B14C872F00_20261103_182445.json"
$B = "--expect","169.254.1.223=194430108183F12E00","--baseline-user","results\calibration_user_194430108183F12E00_20261103_183335.json","--baseline-factory","results\calibration_factory_194430108183F12E00_20261103_183335.json"
$S = "--groups","60","--warmup-groups","30","--save-groups","10","--setup-preview"
.venv\Scripts\python.exe rectify_stereo.py @B @S --label E6_B_s2_mixed
.venv\Scripts\python.exe rectify_stereo.py @B @S --label E7_B_s2_near
.venv\Scripts\python.exe rectify_stereo.py @A @S --preview-crop 39,6,1276,775 --label E8_A_s2_mixed
.venv\Scripts\python.exe rectify_stereo.py @A @S --preview-crop 39,6,1276,775 --label E9_A_s2_near
```

For each run:
1. Position the targets while watching the preview, until every cell shows texture. For Camera A, keep important content inside the crop outline.
2. Step out of view, leaving no people in frame.
3. Press **Space**, keep the scene still for about 12 s of capture, and wait for `RESULT:`.

Q or Esc aborts safely. A cancelled run leaves its folder marked `CANCELLED` and can simply be repeated.

---

## 13. Task 04 direction (proposed, 5 Nov; Task 04A audit, awaiting review)

Research and planning only. Nothing was installed or cloned, no camera was accessed and no validated code was changed. Full audit: [docs/audits/Phase2_Task04A_Streaming_Architecture_Audit.md](../docs/audits/Phase2_Task04A_Streaming_Architecture_Audit.md).

- **Unity WebRTC / Render Streaming: not adopted.** `com.unity.webrtc` 3.0.0 supports Unity 6000.3, but its README has marked it deprecated since 18 Aug 2026. It reportedly fails on 6000.4. Its H.264 is hardware-only (NVIDIA on Windows), and there are open reports of H.264 frame drops and encoder failures on Quest. Render Streaming is experimental (3.1.0-exp.9, Dec 2024) and depends on it. `depthai-unity` is stale and assumes a locally attached camera.
- **Proposed primary stack (Option A, one Unity codebase):**
  - **Encoding:** H.264 Constrained Baseline on the OAK (`VideoEncoder`, no B-frames), one stream per rectified eye.
  - **Gateway:** at CRATER; adds per-frame SEI metadata (camera, eye, sequence number, capture timestamps); remuxes without re-encoding.
  - **Relay and transport:** MediaMTX, then RTSP over TCP to North Terrace.
  - **Receivers:** a Unity Windows build (FFmpeg decoder) and a Unity Quest 3 build (rtsp-client-android, low-latency MediaCodec), behind a shared `IStereoVideoSource`. Both use latest-frame display, sequence-number pairing, freeze and frame-age logging, and reconnection.
  - **Crop and command path:** the Camera A crop is applied by UV at display. The command path is separate.
- **Fallback:** per-eye JPEG over TCP with protocol v2 headers (Task 02 §7). The same fallback is used for both conditions.
- **Bandwidth:** on-device encoding should reduce the PoE load from about 328 Mbit/s raw per camera (Stage D) to roughly 10–20 Mbit/s (estimate, untested).
- **Next step if approved: Task 04B, an offline proof of concept.**
  - Replay saved rectified pairs → libx264 → local MediaMTX (127.0.0.1) → Python reference receiver.
  - Inject 300 and 700 ms stalls and a server restart, and test against gates G1–G3 (audit §6–7).
  - It needs approval to add PyAV to the venv and to download the MediaMTX Windows zip.
  - No cameras and no Unity are needed.
- **Open decisions** (audit §8): H.264 or H.265 and bitrates; per-eye or side-by-side packing; RTSP/TCP, SRT or WebRTC; the CRATER–North Terrace route, firewall, bandwidth and clock sync (needs IT); Unity 6000.3.4f1 installation; the Quest external-texture path; whether participants see a freeze indicator.

### 13.1 COROL integration addendum (5 Nov; source inspection only, awaiting review)

Full report: [docs/audits/Phase2_Task04A_Addendum_COROL_Integration_Audit.md](../docs/audits/Phase2_Task04A_Addendum_COROL_Integration_Audit.md).
- **Repository:** `lab_digital_twin`, branch `albert-phase2` @ `55cfb61`. Read only; nothing was run or imported and no robot was contacted.
- **What it contains:** a FastAPI digital-twin server (:8080, HTTP polling, **no authentication**), a ur_rtde robot library (UR20 192.168.1.11 with a PLC rail; UR3e 192.168.1.13) and a Robotiq gripper HTTP daemon on a NUC (:8081, URL placeholder).
- **Phase 2 task:** exists only as a simulation script with **placeholder poses**. There are no decision points, no task-state API and no persistent event log.
- **Proposed integration:** a new single-commander **Phase 2 task orchestrator** (reusing COROL `robot.py` and its checkpoint helpers, dry-run via `robot_sim`) behind a new **experiment backend**. Participants send only whitelisted AI2 intents. Video, experimental state and robot control are separate paths. The COROL twin server never takes participant traffic.
- **Task 04B is unaffected** apart from three metadata and logging additions (`t_utc` plus host ID, event-record format, avoid ports 8080/8081). The 11 open questions for the CRATER/AIML team are in addendum §13.

### 13.2 Researcher decisions and Task 04B preparation (5 Nov; prepared, NOT RUN, at the review gate)

**Decisions:**
- **Approved:** the provisional architecture (orchestrator, backend, video and Unity kept separate); one Unity codebase with a flexible receiver back-end.
- **On hold:** robot control. COROL's lack of authentication goes to the AIML team (network-isolation and access-control requirements R-NET/R-AC).
- Recorded in [docs/architecture/Phase2_Provisional_Architecture.md](../docs/architecture/Phase2_Provisional_Architecture.md).

**Draft questions for the AIML team:** [docs/coordination/CRATER_AIML_Questions_DRAFT.md](../docs/coordination/CRATER_AIML_Questions_DRAFT.md). **Not sent.**

**Task 04B ([streaming_poc/](../streaming_poc/README.md)):**
- **Environment:** separate `streaming_poc\.venv` with `av==19.0.2`. Its bundled FFmpeg includes libx264, so that build is GPL-licensed (not for redistribution).
- **MediaMTX:** v1.21.3 Windows zip, SHA-256 matched the release checksums. Not Authenticode-signed. **Never launched.**
- **Config:** a localhost-only `config/mediamtx_localhost.yml` with one RTSP/TCP listener on 127.0.0.1:8554, all other listeners off, and loopback-only publish/read on four paths.
- **Scripts:** a synthetic stereo generator, an H.264 Constrained Baseline publisher with SEI (including UTC time and host ID), a reference receiver (pairing, latest-frame-wins, freeze, frame-age and reconnect events) and a G1 analyser.
- **Offline tests:** 41/41 passed with no network and no server. They confirmed Baseline profile, no B-frames, and SEI plus barcode intact through an MPEG-TS round trip.
- **Not exercised:** the RTSP paths against a live server.
- **Next, only on approval:** launch MediaMTX, then a 60 s smoke test, then the G1 run (streaming_poc README).

### 13.3 Task 04B localhost smoke test (5 Nov, 11:32–11:34; approved; overall FAIL)

Results: [streaming_poc/results/smoke_20261105_113138/SMOKE_RESULTS.md](../streaming_poc/results/smoke_20261105_113138/SMOKE_RESULTS.md).
- **Run:** MediaMTX was confirmed bound only to TCP 127.0.0.1:8554. Camera A synthetic stream, 60 s, with one 700 ms burst stall.
- **PASS:**
  - real RTSP publication and decoding (1,140/1,140 frames per eye after joining);
  - L/R identity, matching frame numbers and ordering;
  - image integrity (PSNR 68–73 dB);
  - **all SEI metadata, including UTC capture time and host ID, identical end to end** (2,280/2,280);
  - timing, freeze and loss logging;
  - no security block (one informational Defender cloud lookup);
  - full cleanup.
- **FAIL (S7):** each frame arrives only when the next one is sent (a one-access-unit holdback, about 50 ms at 20 fps). After the stall, a pre-stall frame 783 ms old was shown, then 9 held-back frames.
  - Suspected cause: the FFmpeg RTSP demuxer's H.264 parser (not isolated).
  - Median frame age 64.8 ms, p95 81.6 ms, of which about 50 ms is the holdback.
- The full G1 run has not been started.

### 13.4 Task 04B S7 diagnosis and second smoke test (5 Nov, 11:51–11:53; approved)

Results: [streaming_poc/results/smoke_20261105_115058/SMOKE_RESULTS.md](../streaming_poc/results/smoke_20261105_115058/SMOKE_RESULTS.md).
- **Cause located:** FFmpeg's H.264 parser in the RTSP demuxer.
  - **Not the cause:** the RTP packetiser, MediaMTX or the decoder (offline stage trace, plus a live parser-free probe).
  - On the control stream, raw-complete → parsed release was 45.7 ms median, 748 ms max.
- **Frame-boundary fix:** an end-of-frame SEI after each frame (`--frame-end sei`). Camera A's send → release fell from 50 ms to 2.0 ms median; its frame age fell from 64.8 to **18.1 ms** median (p95 34.4).
  - **Frame-boundary latency: PASS** (A); FAIL on control B, as expected.
- **Receiver freshness safeguard:** rejects pairs whose delay exceeds the recent minimum by more than 100 ms, so it is independent of clock offset. It also discards the obsolete backlog, keeps a strictly increasing display and logs reasons.
  - **Stale-frame rejection: PASS on both streams.** After the stall, the first frame shown was seq 615, 15–25 ms old; 0 held frames were shown.
- **Overall FAIL on S4 (A):** the 58-frame tail was sent after the receiver's 66 s window ended; there was no mid-stream loss. The criterion is unchanged.
- **Offline suites:** 41 + 34 checks pass. Not live-tested: the AUD variant, cross-host clocks, a server restart.
- The researcher confirmed that no Windows Security, Defender or Firewall pop-ups appeared in smoke tests 1 or 2.

### 13.5 Task 04B smoke test 3 (stall + server restart; 5 Nov 12:05; approved): ABORTED

Results: [streaming_poc/results/smoke_20261105_120546/SMOKE_RESULTS.md](../streaming_poc/results/smoke_20261105_120546/SMOKE_RESULTS.md).
- **Prepared and offline-tested first** (41 + 46 checks):
  - publishers start before receivers; receivers stop on the publisher's done flag plus a drain;
  - reconnect backoff capped at 1 s;
  - two freshness measures: relative excess, and absolute age with bounds and clock source;
  - labels `fresh` / `late` / `fresh_relative` / `relative_adapted` / `unverified`, so a persistently delayed stream is never called fresh;
  - re-baseline logging and a restart regression test.
- **What went wrong:** the new orchestrator script aborted at t = 35 s, when MediaMTX was stopped for the restart. A PowerShell function return value included a log line; the error handler then terminated the test processes.
- **Verdicts:** the restart was not performed. S1, S2, S3 and S8 PASS. S4, S5–S7 and F formally NOT_TESTED. R1–R5 NOT_TESTED.
- **Partial pre-abort data:** consistent with the fixes (send → release 2.5 ms median; the 15 s stall handled with 0 stale frames shown; all pairs `fresh` with absolute age within limit).
- **Next step:** the script is fixed and its no-launch self-test passes. **A re-run needs approval.**
- The researcher later confirmed no Windows Security or Firewall pop-up during the aborted run.

### 13.6 Task 04B smoke test 3 re-run (5 Nov 12:11; approved): all criteria PASS, with a timing deviation

Results: [streaming_poc/results/smoke_20261105_121101/SMOKE_RESULTS.md](../streaming_poc/results/smoke_20261105_121101/SMOKE_RESULTS.md).
- **Gate:** self-test PASS; offline 41/41 + 46/46.
- **Run:** both streams with the end-of-frame SEI and the freshness safeguard. Publishers started first; receivers stopped on the done flag.
- **Verdicts:**
  - S1 (both MediaMTX instances), S2, S3, S8: PASS.
  - S4: PASS (96.0 %, original rule).
  - S5a–e, S6, S7, S7a (2.7 ms release), S7b: PASS.
  - F1–F3: PASS (absolute age 26 ms median, ±1 ms same-host clock).
  - R1–R5: PASS (display resumed 2.0 s after publisher reconnect; no stale replay; reference reset; integrity across restart).
  - F3b: NOT_TESTED (out of scope).
- **Deviation:** the restart was issued at t = 40.85 s, not 38 s (slow Windows socket queries in the orchestrator), giving about 6 s of downtime and about 18 s of post-restart streaming instead of about 22 s.
- **Instrumentation flaw:** the publisher logs `link_up` at a lazy open before any real connection, and its reconnect attempts block the capture loop (126 late frames). The fix is proposed, not applied.
- The full 11-minute G1 run has not been started.

### 13.7 Task 04B final fixes and full G1 run (5 Nov 12:27–12:57; approved)

Results: [streaming_poc/results/smoke_20261105_122716/G1_RESULTS.md](../streaming_poc/results/smoke_20261105_122716/G1_RESULTS.md).

**Fixes made first:**
- The publisher logs `link_up` only after a successful write.
- Generation is non-blocking, with a sender thread and a bounded 2-pair latest-frame queue.
- The orchestrator restarts MediaMTX on the scheduled clock.

**Pre-run gate:**
- Self-test PASS.
- Offline suites 41 + 46 + 21 (new) checks.
- GIL-release check PASS.
- No camera, COROL, robot or Unity code involved.

**Result: G1.1–G1.7 PASS on both cameras:**
- capture → display age 29.5 / 46.2 / 113 ms (A) and 25.8 / 42.7 / 111 ms (B), median / p95 / max;
- 0 pairing or metadata errors over about 47,000 frame-eyes;
- display resumed 1.9 s after reconnect;
- generation continued through the outage.
- **Restart timing was exact:** issued at 545.00 s, as planned.

**Departures and failures:**
- **Standby:** Windows Modern Standby (idle timeout, 12:37:16–12:57:35) froze every process at t ≈ 615 s; the planned final 45 s did not run in real time.
- **S8:** the cleanup check raced the post-wake shutdown.
- **P2:** a stale in-hand frame (about 1.65 s old) was sent at reconnect; the receiver rejected it.
- **S7b:** the strict first-frame rule was not met (76 ms first frame).
- **S7a on camera B:** one 306 ms frame.
- **Python CPU and memory:** not measured (launcher PIDs sampled).

**Finding:** a recurring ~300 ms localhost transport delay upstream of MediaMTX's fan-out caused all the queue discards while connected and most of the display freezes. It matches the Windows TCP minimum RTO (hypothesis).

**Review gate:** accept this run or repeat it. The proposed fixes need approval.

### 13.8 Task 04B G1 rerun preparation (5 Nov, afternoon; offline only, nothing launched)

No MediaMTX, live stream, camera, COROL, robot or Unity was involved. The G1 evidence is unchanged; one new read-only diagnostic file was added to it (`delay_coincidence.txt`).

**The four approved corrections:**
1. **Keep-awake:** `run_smoke_restart.ps1` holds `SetThreadExecutionState(CONTINUOUS | SYSTEM_REQUIRED | DISPLAY_REQUIRED)` for the run and releases it in a nested `finally` (`keepawake.json`). This is a per-process request; no power setting, policy or permission is changed. Kernel-Power 506/507 events during the run are read (read-only) into `cleanup.json`.
2. **No stale frame at reconnect (P2):** the publisher writes the container header, which for RTSP is the connection, *before* it takes a pair from the queue. A pre-encode age guard (`--max-send-age-ms`, default 150 ms; burst frames exempt) is added as a backstop. Generation and the 2-pair queue are unchanged.
3. **Resource sampling:** the venv launcher's `python.exe` child, the real interpreter (`Python313\python.exe`), is resolved and sampled (`pids.json`), and system-wide CPU and memory go to `system.csv`. Resolution happens after the receivers start, so the launch timeline is the same as in G1.
4. **Cleanup:** a bounded wait (`-ExitWaitSeconds`, 60 s) for every launcher and interpreter to exit runs before the cleanup check. Leftovers are recorded first, then stopped. The abort path now stops interpreters too, where stopping only the launchers would have orphaned them.

**Offline results:**
- existing suites: 41/41, 46/46, 21/21 (×2), GIL check PASS;
- new `test_publisher_reconnect.py`: 19/19 (×2). Its control run with the old lazy connect reproduces the stale frame (P2 FAIL), and the fixed publisher passes P2 as scored by `smoke_check`'s unchanged code;
- new `test_rerun_prep.py`: 10/10. It confirms that the preserved G1 evidence still scores P2 FAIL at 1,647 ms and S8 FAIL, with no evidence file changed;
- orchestrator `-SelfTest`: PASS. It now covers keep-awake held and released, system sampling, interpreter resolution and the bounded wait.

**~300 ms delays (bounded review of existing logs; `tests/delay_coincidence.py`):**
- **Verified from the data:**
  - 210 delayed frame-eyes before the standby, with fault windows excluded. The delays are quantised: 162 fall in 300–325 ms and 37 in 250–275 ms.
  - They are unrelated to frame size or keyframes (median 50,169 B against 50,168 B; 4.8 % keyframes against 5.0 %).
  - The episodes are mostly independent across the four publish connections. For example, A-left (77 episodes) and A-right (same publisher process, same MediaMTX) never coincide.
  - The episodes are unevenly spread: A-left 77, B-right 23, A-right 13, B-left 4.
  - The traced frame was delayed after the publisher's write had returned and upstream of MediaMTX's fan-out (§13.7).
- **Hypotheses (unverified):**
  - per-connection TCP retransmission on loopback at the Windows minimum RTO (fits the quantum and the independence);
  - a per-connection read stall inside MediaMTX (fits the independence less naturally).
  - A host-wide or process-wide pause is **disfavoured** by the independence.
- Confirmation would need a packet capture or TCP statistics (approval needed). Nothing was changed.

**Remaining risks for the rerun:**
- S7a and S7b may fail again from these delays and from the strict first-frame rule, which is unchanged.
- The keep-awake request cannot prevent lid-close, power-button or screen-lock suspension.
- The fixes are verified offline only; the RTSP connect-first path has not run against a live server.

**Status:** ready for the full G1 rerun on approval (commands in `streaming_poc/README.md`).

### 13.9 Task 04B G1 rerun (5 Nov 15:11–15:22; approved): G1.1–G1.7 PASS, uninterrupted

Results: [streaming_poc/results/smoke_20261105_151122/G1R_RESULTS.md](../streaming_poc/results/smoke_20261105_151122/G1R_RESULTS.md).

The plan, configuration and criteria were unchanged, and no functional change was made after approval.

**Run conditions:**
- Full 660 s in real time.
- Keep-awake held to the end; no standby; no clock discontinuity (UTC against monotonic drift < 1 ms).
- Restart issued at 545.017 s (planned 545).
- All processes exited before the cleanup check; port 8554 closed.

**Result: G1.1–G1.7 PASS on both cameras:**
- capture → display 35.3 / 36.2 ms (A) and 36.5 / 37.6 ms (B), median / p95;
- 0 pairing or metadata errors over 51,900 frame-eyes;
- resume 1.93 / 1.94 s after reconnect.

**Fixes verified live:**
- **P2 PASS:** the first frame after reconnection was 110 / 99 ms old (G1: about 1,650 ms). The reconnection blocked 1.57 s in the header write, before any frame was taken; the age guard never fired.
- **S8 PASS; S7a PASS.**
- **Python resources measured** (interpreters):
  - publishers 67–74 % of one core and 191 MB;
  - receivers 28–37 % and 45 MB;
  - MediaMTX 34 % and 75 MB;
  - system 22 % median busy over 20 logical CPUs, memory load 49–51 %.
- **Bitrate:** 15.9 Mbit/s per camera.

**S7b FAIL (both cameras), on the sub-rule "at least one rejection after every stall":**
- The drop stall sends no frames, so there is nothing to reject.
- In G1 the same sub-rule was met only through later, delay-induced rejections.
- Every substantive outcome passed: 0 stale pairs displayed, 0 held frames shown, 0-frame recovery.
- Not re-scored; amending the sub-rule is the researcher's decision.

**The ~300 ms delays did not recur:**
- max 74 ms send → release;
- 0 discards while connected;
- freezes only at the injected faults.

The cause of the difference is unverified (hypothesis: the idle-machine power state in G1).

**Firewall log:** 4 informational events for an unrelated system `OICE_16_…` rule pair (interpretation). No security block was observed; operator confirmation of no pop-up is pending.

**Review gate:** close Task 04B, then decide on Unity Windows reception. Both need the researcher's approval.

### 13.10 Task 04B closed (researcher decisions, 5 Nov)

1. **Task 04B is complete at its original G1 gate.** G1.1–G1.7 passed on both synthetic cameras in the uninterrupted rerun (§13.9).
2. **S7b stays FAIL exactly as recorded** (12:27 and 15:11 runs).
   - **The flaw:** requiring at least one rejection after *every* stall is inappropriate for a drop stall, where no delayed frames arrive. The count is also cumulative from the stall start, so in G1 unrelated later rejections satisfied it.
   - **A versioned correction, S7b v2, is proposed for future tests only** (`streaming_poc/README.md`, "Criteria versions").
   - No verdict is changed retroactively.
3. **Other open items:** F3b stays NOT_TESTED. The intermittent ~300 ms localhost delays stay an unresolved observation (§13.7–13.9). No further localhost endurance tests are required at this stage.
4. **All Task 04B evidence is preserved** under `streaming_poc/results/`.
5. **Unity installation corrected:** Unity 6.3 LTS **6000.3.28f1 installed** (researcher, 5 Nov). A Universal 3D (URP) test project opens and Play Mode works. The disposable test project is named `My project`; it is not used for development. Android Build Support and Quest deployment are **not verified**. The recovered Side Quest project was saved with 6000.3.4f1 and stays read-only. This supersedes the earlier "Unity not installed / 6000.3.4f1 required" statements.

**Next:** Task 05 (Unity Windows reception). The plan is in [docs/plans/Phase2_Task05_Unity_Windows_Reception_Plan.md](../docs/plans/Phase2_Task05_Unity_Windows_Reception_Plan.md). It awaits approval, and no Unity code has been written.

### 13.11 Task 05 compatibility milestone (5 Nov, approved; offline synthetic input only)

The researcher approved M1 preparation (12 decisions, plan §10). They include:
- **S7b v2:** adopted for future tests; the v1 FAILs are preserved.
- **M1 criteria:** retained with their exact thresholds.
- **Licensing:** a university review before external distribution.

**Done:**
- **New project** `unity/Phase2Client`: Unity 6000.3.28f1, URP 17.3.0, linear colour space, local Git repository with no remote. Binaries and `test_results/` are git-ignored.
  - It was created with the Editor's `-createProject` and configured to URP, because the Hub's Universal 3D template package was not obtainable offline.
- **Pinned and verified downloads:**
  - FFmpeg.AutoGen 9.0.1.1 (MIT; SHA-512 matches the NuGet catalog; NuGet signature valid);
  - BtbN FFmpeg `n9.0.2-39-g7adfbe40dc` win64 LGPL shared (SHA-256 matches; **LGPL-3.0-or-later**, not 2.1; not the same build as PyAV's 9.0.2).

**Result: compatibility checks C01–C09 PASS** in the Editor (EditMode 4/4) and in a Windows standalone Mono player:
- DLL loading from the project's own plugin folder, with all 37 required exports;
- decode of 120 frames per eye with intact SEI metadata;
- PSNR ≥ 62.9 dB;
- 120 complete pairs;
- two-thread decode;
- interrupt stop in 1 ms;
- exact R8 GPU texture round trip on D3D12;
- clock agreement with Python.

**Findings:**
- Unity's Mono `Stopwatch` is not QPC (6.75 h epoch offset); fixed by calling QPC directly.
- Frame N's end-of-frame marker travels in frame N+1's packet.

**Verdict:** the decoder route is suitable, and the full M1 receiver can proceed (offline first; the live tests T3 and T4 need approval). Evidence is in `unity/Phase2Client/test_results/compat/COMPAT_RESULTS.md`.

### 13.12 Task 05 M1 offline receiver (5 Nov, approved; offline only)

**Implemented in `unity/Phase2Client`** (plan §13), with the validated FFmpeg dependencies unchanged:
- Camera A, both eyes on two FFmpeg reader threads;
- a C# port of the Python presenter (pairing by verified seq, freshness, monotonic display, reconnect reset);
- bounded luma buffers;
- the left eye displayed with the Camera A crop, plus a developer-only right-eye inset and overlay;
- logs in the Python receiver schema;
- the backend behind a replaceable seam.

**Offline results, all PASS:**
- **Differential tests:** the C# presenter matches the Python oracle on 20 traces with 0 mismatches. These include replays of the recorded smoke 1 and of the G1 rerun (cameras A and B).
- **EditMode:** 30/30.
- **Full receiver, real time:** run on a recorded scenario (burst stall, drop stall, 5-frame drop, link break and reconnect with stale re-delivery) in Editor Play Mode and in the Windows player. Each run's logs pass `verify_unity_run.py`: an exact oracle replay of Unity's presenter inputs and 11 scenario checks.
- **Rendering:** pixel-exact (max diff 0 over the 1238 × 770 crop) on D3D12.
- **Image:** at least 62.9 dB PSNR against the source.
- **Player timing (indicative):** frame interval p99 17.4 ms at 60 Hz.

**The M1 criteria are not scored** (they need T4).

**Untested:**
- RTSP from MediaMTX in Unity;
- live reconnect;
- same-host absolute age;
- Defender or firewall for the Unity executable;
- IL2CPP and Quest.

**T3 (60 s Unity Windows smoke) is ready for approval:**
- **Synthetic source:** MediaMTX (verified localhost config) plus `publish_synthetic.py --camera A --frame-end sei` (60 s, no faults).
- **Receivers:** the Python reference receiver for camera A, plus Unity started manually (decision 11): `Builds\M1\Phase2M1.exe -m1Mode rtsp -m1Seconds 75 -m1Label t3 -m1Quit`.
- **Afterwards:** `verify_unity_run.py` (oracle replay) and a comparison with the Python receiver on the same stream.
- **Open decision:** the orchestrator always restarts MediaMTX and starts both cameras. Either run T3 by hand (losing its preflight, keep-awake and cleanup checks), or approve a small, versioned orchestrator option (`-Cameras A`, `-NoRestart`).

### 13.13 Task 05 T3: first live Unity RTSP smoke test (5 Nov 17:01–17:03, approved)

Results: [unity/Phase2Client/test_results/m1_smoke_20261105_170126/M1_SMOKE_RESULTS.md](../unity/Phase2Client/test_results/m1_smoke_20261105_170126/M1_SMOKE_RESULTS.md).

**Set-up:**
- **Orchestrator v2** (`-Cameras A`, `-NoRestart`, `-ExternalProcess`, `-PlanOnly`). Defaults unchanged: the plan reproduces the G1 rerun arguments exactly; self-test PASS.
- The publisher ran 100 s, outlasting Unity's 75 s session.
- Unity was started by hand.
- The Python reference receiver ran in parallel on the same streams.

**Result: PASS for everything testable:**
- **Live decode:** 1,475 frames per eye, 0 errors.
- **Pairing:** 1,464 displayed pairs, all correct.
- **Metadata:** equal to the publisher's record.
- **Image:**
  - the displayed frames equal Python's PSNR on every common frame (68–73 dB);
  - the left-eye render is pixel-exact.
- **Freshness:** same-host absolute age, Unity 27.8 / 39.3 ms median / p95 (Python 39.0 / 39.9).
- **Oracle replay of the live run:** exact.
- **Shutdown and cleanup:** clean.
- **Security logs:** 0 Defender, AppLocker or Firewall events. Operator confirmation of no pop-ups pending.
- **Python side (`smoke_check`):** all testable criteria PASS; fault and restart criteria NOT_TESTED by design.

**Not scored:** the M1 criteria (T4).

**Before T4:**
- an M1 scorer;
- S7b v2 in `smoke_check`;
- Unity resource sampling;
- the `cleanup.json` cosmetic fix;
- optionally a right-eye inset check and the splash/start-up handling (about 8 s from launch to first frame).

### 13.14 Task 05 T4 preparation (5 Nov, approved; offline only, T4 NOT run)

The plan §15 holds the full schedule and criteria.

**Prepared:**
- **M1 scorer** (`score_m1.py`, M1.1–M1.10 with the retained thresholds). A run is formal evidence only in the T4 configuration; T3 scores NOT FORMAL.
- **S7b v2** as a separate key; v1 and its verdicts unchanged.
- **Orchestrator v3:** Unity player CPU and memory sampling, and its exit time; the `[]` fix.
- **Unity instrumentation:** shutdown timing, render-submission time, and the right-eye display check (pixel-exact offline).
- **Frame-age stage definitions:** physical presentation is not measured.

**Offline tests, all PASS:**
- streaming_poc: 41, 46, 21, 19, 10 + 15 (S7b v2) + 13 (orchestrator plans);
- scorer 49;
- Unity EditMode 30, Play Mode 1, plus the player replay with the oracle.

**T4 schedule:**
- **Publisher:** 400 s.
- **Faults:** bursts at 60 s (300 ms) and 120 s (700 ms); a drop stall at 180 s (700 ms); a 5-frame drop at 240 s; MediaMTX restart at 300 s (down 5 s).
- **Unity:** launched at about 3 s, session 380 s.
- **Measurement window:** 20–380 s.
- **Approval:** awaiting.

### 13.15 Task 05 T4: six-minute live fault-injection test (5 Nov 17:35–17:42, approved)

Results: [unity/Phase2Client/test_results/m1_t4_20261105_173459/T4_RESULTS.md](../unity/Phase2Client/test_results/m1_t4_20261105_173459/T4_RESULTS.md).

**Run:**
- Ran detached from the Claude Code session (WMI-started runner); completed, saved its evidence and cleaned up by itself.
- Exit codes 0; nothing left; 8554 closed.

**Formal M1 result: FAIL.**
- **Pass:** M1.1–M1.3, M1.7–M1.10. Age 27.2 / 40.9 ms; frame interval p99 17.5 ms; pixel-exact display; clean shutdown.
- **Fail:** M1.4 (S7b v2: the strict 0-frame recovery rule, and the pre-stall frame at a drop stall); M1.5 (the ~300 ms transport delays recurred, so a freeze that began before the 120 s stall was not matched to it); M1.6 (`score_m1.py` omitted the validated R3's 200 ms in-flight grace; the flagged frame was 31 ms old, displayed 4 ms after the stop).
- The oracle replay of Unity's live run is exact. The Python reference shows the same delay episodes and also FAILs S7b v2.

**Not re-scored; no fixes made. Decisions are needed** on the M1.4, M1.5 and M1.6 definitions and the scorer correction before M1 can close.

### 13.16 Task 05 M1 scoring corrections and supplementary T4 re-score (6 Nov 2026; offline, approved)

Results: [unity/Phase2Client/test_results/m1_t4_rescore_v2_20261106/RESCORE_RESULTS.md](../unity/Phase2Client/test_results/m1_t4_rescore_v2_20261106/RESCORE_RESULTS.md). No live test, no MediaMTX, no camera.

**Approved and implemented (thresholds unchanged):**
- **`score_m1` scorer 1.1:** M1.6 applies R3's existing 200 ms in-flight grace. Scorer 1.0 is kept only to reproduce the recorded verdicts.
- **S7b v3** (`smoke_check.s7b_v3_check`; reported only when requested, so v1 and v2 and all old reports reproduce exactly):
  - no duplicate 0-frame recovery rule, so M1.4's ≤ 2 frames is authoritative;
  - the pre-stall frame is held only if its send→receipt time exceeds 50 ms;
  - transport delay, freshness and held-frame display are reported separately.
- **M1 criteria v2, labelled POST-HOC:**
  - M1.4 uses S7b v3;
  - M1.5 also accepts a freeze that began earlier and is still active at the stall end, recording the condition and the freeze's own onset and duration;
  - a non-gating unscheduled-freeze measure is added.
- **T4 erratum** appended to `T4_RESULTS.md`: Python recovered in 0 frames and Unity in 1–2; both obeyed their freshness rules.

**Verdicts on T4:**
- **Original, recorded: FAIL** (criteria v1, scorer 1.0). It is unchanged and reproduced exactly.
- Criteria v1 with scorer 1.1: FAIL, with only M1.6 changing to PASS.
- **Supplementary: PASS 10/10** (criteria v2, scorer 1.1; post-hoc).

**Non-gating measure:** 93 unscheduled freezes in 360 s (15.5 per minute). In Unity the median was 382 ms and the maximum 715 ms, excluding 2 freezes that ran into stalls; Python's figures were the same. The publisher discarded 287 pairs while connected. **The ~300 ms delay issue is unresolved.**

**Tests:**
- new: `test_s7b_v3` 40/40 and `test_score_m1_v2` 45/45;
- unchanged and passing: `test_s7b_v2` 15/15, `test_score_m1` 49/49, `test_streaming_poc` 41/41 and `test_freshness` 46/46.

The G1 rerun and T4 Python smoke criteria are recomputed identically. All 388 evidence files are hash-identical, apart from the appended erratum.

**Next:** the researcher decides on closing M1 on the supplementary result, and on the first real Camera A preview (plan §17).

### 13.17 Task 06: Camera A to Unity, offline readiness and Stage 1 approval (6 Nov 2026)

Documentation only; this section was added with the researcher's approval. No validation file was changed: the camera_validation sources, results and venv are untouched, and the three safeguard modules the gateway imports are SHA-256 pinned.

**Task 05 M1: CONDITIONALLY VALIDATED** (researcher decision).

| Item | Result |
|---|---|
| Original T4, criteria v1 | FAIL, 7/10 (recorded) |
| Supplementary T4, criteria v2 (post-hoc) | PASS, 10/10 |
| Receiver correctness | Supported |
| Unscheduled freezes | Unresolved |

**Offline readiness (plan [docs/plans/Phase2_Task06_CameraA_Unity_Preview_Plan.md](../docs/plans/Phase2_Task06_CameraA_Unity_Preview_Plan.md)):**
- **New [`camera_gateway/`](../camera_gateway/README.md):**
  - its own venv (depthai 3.11.0, numpy 2.4.6, av 19.0.2), with builds identical to `camera_validation/.venv` and `streaming_poc/.venv`;
  - StereoDepth rectification exactly as E1, and on-device H.264 Baseline per eye;
  - FrameMeta and frame-end SEI; a GOP-aware latest-frame queue; a template muxer with no encoder;
  - the validated safeguards;
  - `--live` required to touch hardware.
- **Unity `-m1Source camera`:** the barcode check is "na", FLAG_SYNTHETIC must be clear, and everything else is unchanged. The synthetic mode is unchanged.
- **Crop:** `RectInt(39, 6, 1238, 770)` was already applied in M1; the Task 05 plan errata are added.
- **Clock fixture:** the stale Unity clock test (C09) is fixed.
  - The original failure is preserved (`unity/Phase2Client/test_results/task06/editmode_results.xml` and `test_results/compat/editor_compat_20261106_114037.json`).
  - C09 now uses a reference made in the current Windows boot session (`Tools/make_clock_reference.py`) and reports a reference from another session as stale.
  - Rerun: EditMode 43/43, C09 PASS (offset difference 0.00 ms).
  - My first attempt did not compile (`Environment.TickCount64` is not in Unity's API profile); its log was removed by my retry and the fix uses `GetTickCount64`.

**Stage 0 (6 Nov 12:06, offline): PASS** (`camera_gateway/results/stage0_20261106_120607`).
- **Gateway suite:** 73/73.
- **Plan-only mode:** checked.
- **Dependencies:** freeze = the lock file; DepthAI and PyAV builds identical to the validated venvs.
- **Pinned safeguard sources:** unchanged.
- **Baselines** present.
- **MediaMTX config hash:** equals the T4-verified value.
- **DepthAI crash dumps:** 1, the 4 Nov Camera B dump.
- **Laptop:** on Wi-Fi at the time, so not isolated.
- Two earlier Stage 0 FAILs (12:04, 12:05) were bugs in the checker (whole-RECORD comparison; a text scan that matched message strings). They are kept as recorded.

**Connection procedure and bootloader state.** The procedure supports the bootloader state without persistent change:
- **Before connecting:** `connect_verified` requires the device in `X_LINK_BOOTLOADER`.
- **Connecting:** `dai.Device(info)` loads the DepthAI firmware into RAM; nothing is flashed.
- **After closing:** the device reboots into its bootloader, and post-run verification waits for that before re-reading the calibration.
- **Static scan (AST)** of the gateway and the pinned modules: no flash, bootloader, IP, calibration-write or factory-reset call. The only IR call is `capture_stereo.py:180` with 0.0.
- **Prior evidence:** Camera A E1, E3 and E5 connected from the bootloader, with calibration unchanged and the device back in the bootloader (`read_ok`). Bootloader 0.0.26 was recorded on 3 and 4 Nov.
- **New gateway check:** it reads the bootloader back (read-only) and refuses unless it is 0.0.26.

**Stage 1: APPROVED by the researcher on 6 Nov 2026** (Camera A only, 30 s, files only; Stage 2 NOT approved).
- **Runner:** `camera_gateway/tools/run_stage1.ps1` (keep-awake, disarm file, one retry only if discovery finds no camera).
- **Criteria H1–H13:** defined before the run in `camera_gateway/tools/analyse_stage1.py`. H8 was revised before the run, after the dry run.
- **Dry runs (fake device):**
  - the runner is tested;
  - the designed-to-fail runs (bootloader 0.0.29; a 40-frame device gap) FAIL as intended;
  - the wait timeout and the disarm both end with nothing contacted.
- **Results:** recorded in §13.18 when available.

### 13.18 Task 06 Stage 1: Camera A on-device H.264, 30 s, files only (6 Nov 12:28–12:29, approved)

Results: [camera_gateway/results/stage1_review_20261106/STAGE1_RESULTS.md](../camera_gateway/results/stage1_review_20261106/STAGE1_RESULTS.md). Evidence: `camera_gateway/results/stage1_runner_20261106_122209/` and `gw_20261106_122812_A_stage1/` (unchanged). Run once; no MediaMTX, no Unity, no other device.

**Result: PASS on H1–H12; H13 is information only.**

| Criterion | Result |
|---|---|
| Identity | Camera A from bootloader state |
| Bootloader | 0.0.26 before and after (back in bootloader, `read_ok`) |
| Calibration | Equal to both baselines before start, in session and after the run |
| AutoCalibration | OFF |
| IR | Off, acknowledged before and after start |
| **On-device encoding** | **H.264 Baseline encoding of both rectified eyes works** (CBR 8 Mbit/s, IDR every 20, no B-frames, profile 66) |
| Frames | 601 per eye, seq 0–600, **0 gaps** |
| Device interval | 50.000 ms |
| Host vs device clock | Fit residual p99 0.1 ms; drift 9 ppm |
| L/R skew | Max 0.034 ms |
| Raw output | 601/601 decode, 0 errors |
| Packaged MPEG-TS | 541/541 decode, metadata intact |
| Shutdown | Clean; no new crash dump |

**Observations (not failures):**
1. **Fixed on-device latency**, capture to host receipt: median about 73 ms, p95 about 77 ms, max 94 ms in steady state. The expected Unity capture-to-display age is about 85–95 ms, so the synthetic M1.3 figures do not apply.
2. **Start-up transient:** a 650 ms delivery stall about 3 s after the pipeline started, with no frame lost (the Stage D pattern). The 150 ms age guard dropped GOPs seq 0–19 and 60–99 (60 frames per eye not sent); nothing was dropped after seq 100.
3. **Bitstream:** AUD on every access unit; SPS/PPS on every IDR.
4. **DepthAI advisory:** optional bootloader 0.0.29 available. Not applied, as decided.
5. **Crop:** all persistent rectification border lies outside the approved crop in both eyes.

**Stage 2 (MediaMTX and the live Unity preview): NOT started.** It awaits the researcher's approval.

### 13.19 Task 06 Stage 2: live Camera A → gateway → MediaMTX → Unity preview (6 Nov 12:55–12:58, approved)

Results: [camera_gateway/results/stage2_review_20261106/STAGE2_RESULTS.md](../camera_gateway/results/stage2_review_20261106/STAGE2_RESULTS.md). Evidence (unchanged): `camera_gateway/results/stage2_runner_20261106_125516/` and `gw_20261106_125623_A_stage2/`.

**Preparation** (6 Nov, offline; approved): Stage 2 runner `camera_gateway/tools/run_stage2.ps1`, gateway `--stop-file`, and the analysis with criteria S1–S11.
- **Dry runs** (fake device, fake loopback listener, fake Unity stand-in): plan-only; success; gateway refusal; Unity hang and crash; operator abort. All handled safely, two of them launched detached through WMI.
- **One runner bug** (a nested socket list) failed safely and was fixed.
- **Tests:** gateway 74/74, analysis 23/23.

**Live run (approved; once). Integrity PASS on S1–S11, including the oracle replay.**

| Item | Result |
|---|---|
| Identity and bootloader | Camera A from bootloader state; bootloader 0.0.26 before and after |
| Calibration | Equal to both baselines before start, in session and after the run |
| AutoCalibration | OFF |
| IR | Off, acknowledged before and after start |
| MediaMTX | TCP 127.0.0.1:8554 only |
| Frame metadata | All 2249 Unity arrivals identical to what the gateway sent |
| Stereo | Pairs intact; device L/R skew max 0.034 ms |
| Camera sequence gaps | 0 |
| Stale frames | None displayed |
| Render checks | Pixel-exact at crop 1238 × 770 |
| Shutdown | Clean: no process left, port 8554 closed, Unity exit 0, no new crash dump |

**Latency, capture → Unity selection (displayed pairs, n = 1054):** median **90.7 ms**, p95 99.4 ms, max 121.3 ms. Of this:
- capture → host: 73.8 ms (on-device; p95 75.3);
- host → selection: 17.0 ms.

**The researcher's "few dropped frames" are 6 recorded freezes of 0.77–1.36 s.**
- **Cause:** each followed a 210–316 ms blocked RTSP write on the gateway's **right-eye** connection to MediaMTX. Every other write took ≤ 15 ms.
- **In Unity:** the late pairs were rejected by the freshness safeguard (8; none shown).
- **In the gateway:** the 150 ms age guard then dropped the rest of that GOP to keep the stream decodable (≤ 1 s at keyint 20).
- **Also:** two single 100 ms frame skips (a left frame about 51 ms late), and the start-up GOP (seq 0–19), as in Stage 1.
- **Classification:** the camera and the receiver behaved correctly. It is the unresolved ~300 ms localhost transport-delay issue, now on the gateway → MediaMTX leg, amplified by GOP-level dropping. Why only the right eye was affected is not established.

**Options for review (no change made):**
- raise the gateway's send-age guard above the stall size;
- a shorter keyframe interval;
- a packet-level investigation of the loopback stalls.

No further live session until the researcher decides.


---

### 13.20 Task 07: AI2 supervisory interface, S1 and S2 complete; receiver races R1/R2 fixed (6–7 Nov 2026; offline)

**Documentation only.** No camera, MediaMTX, COROL or robot was used in Task 07. All video is offline replay.

**Design.** Site Window revision 2 was approved, together with these researcher decisions:
- Allow and Intervene may be made from Inspect;
- nudges are incremental, one at a time, never batched;
- corrections are modelled with the element held (provisional);
- participants see the commanded offset only;
- Retry resets the correction only once the new attempt has started;
- simulation limits are provisional.

[Proposal](../docs/plans/Phase2_Task07_AI2_Interface_Design_Proposal.md).

**S1 complete.** Pure C# AI2 state machine, simulated backend and schema v1.1. 51/51 tests at the time. [S1 results](../docs/plans/Phase2_Task07_S1_Implementation_Results.md).

**S2 complete.** Two-camera supervisory video in `unity/Phase2Client`:
- the approved opt-in `createDisplay` flag;
- one validated receiver per camera;
- Camera A is the real E1 replay; Camera B is SYNTHETIC, labelled "SIMULATED CAMERA B";
- camera and zoom only during Inspect;
- decision-time logs carry both cameras' displayed frames.

[S2 results](../docs/plans/Phase2_Task07_S2_Implementation_Results.md).

**C09.** An NTP step of −2488 ms at 15:58 on 6 Nov explains both failures. The reference was regenerated through the established tool, and C09 passes. Evidence: `unity/Phase2Client/test_results/c09_investigation_20261106/`.

**R1 and R2 fixed** (approved).
- **R1:** all presenter events are emitted inside the presenter lock, in op order.
- **R2:** pixels are stored before the presenter can select a pair, and `LumaStore.CopyPair` copies both eyes atomically.
- **Tests:** seven deterministic and stress tests reproduce both races on the preserved pre-fix code and pass after the fix.
- **One harness fix:** the S2 view-log rows had a timestamp alignment defect, found during the regression. It was fixed and re-verified.

[Part A](../docs/plans/Phase2_Task07_S2_PartA_Receiver_Race_Fixes.md).

**Regression (7 Nov): PASSED.**

| Suite | Result |
|---|---|
| EditMode | 109/109 |
| PlayMode | 12/12 over 6 runs |
| Python-oracle match | every receiver run matched the validated Python presenter |
| M1 Windows player | 4/4, including the pixel-exact render check |
| S2 Windows player | 2/2 |

**Git checkpoint:** a local commit in `unity/Phase2Client` (no remote), marking S2 complete and the regression baseline validated.

**Next:** Task 07 **S3, the Site Window Windows prototype** (approved, not started).

### 13.21 Task 07 S3: Site Window Windows participant interface, implemented and verified (11 Nov 2026; offline; awaiting review)

**Documentation only.** No camera, MediaMTX, COROL, robot or network was used. All video is offline replay: real Camera A E1 imagery, about 20 s; SYNTHETIC Camera B, about 40 s.

**Built** in `unity/Phase2Client/Assets/Phase2/SiteWindow/`:
- an engine-free participant model: string table plus a view-model over the S1 machine;
- a uGUI + TextMeshPro interface in IBM Plex (OFL, from IBM's official releases);
- `S3Session`, which reuses the S1 harness and the S2 feeds and view;
- a start screen, a walkthrough scenario, and a scripted verification run with deterministic faults.

**One additive change to existing code:** the `SupervisoryVideoView.FitMargin` field. Its default keeps S2 unchanged; S3 uses a 1:1 plate. The player is `Builds/S3/SiteWindow.exe`, launched with `Tools/run_site_window.ps1`.

**Verification:**

| Suite | Result |
|---|---|
| EditMode | 126/126 (17 new) |
| PlayMode | 3/3 |
| Scripted player session | 63/63 checks |
| On-screen plate at 1× (1920 × 1080) | 953,260 px, max diff 0 |
| `Tools/verify_s3_run.py` | PASS: oracle replay of both receivers, view rules, log integrity |
| M1 and S2 Windows players | 2/2 and 2/2 |

**C09** failed only because the laptop had rebooted (a per-boot reference). The reference was regenerated with the established tool and the old one preserved: `unity/Phase2Client/test_results/c09_boot_session_20261111/`.

**Fixed during S3** (S3 code only): a trial-start clock-ordering defect, which the same latent ordering in `S2Session` shares (not changed); the fonts fallback; Editor CanvasRenderers; the developer-panel placement.

**R3** (about 18 s FFmpeg start-up) recurred once, on the first launch of a fresh build.

**Open decisions** S3-1 to S3-7 (Begin screen, simulation tag, video that reflects corrections, video thresholds, hover logging, display spec, S2 harness fix). See the report: [S3 results](../docs/plans/Phase2_Task07_S3_Implementation_Results.md).

**Git:** not committed (the last commit is the S2 checkpoint `f59cf1f`). A checkpoint commit is suggested after review.

**Update (12 Nov 2026):** the researcher accepted S3 as the functional baseline. It is committed in `unity/Phase2Client` as **`e418f620663e5cf7c84fa37127758d12bf11a02d`** (local `master`, no remote; 143 files; builds, raw evidence and binaries excluded by `.gitignore`).

**Next:** the researcher reviews the prototype. S4 and the Quest 3 work are not started.

### 13.22 Task 07 S3.1: revised placement, recovery and correction CONOPS, implemented and verified (12 Nov 2026; offline; awaiting review)

**Documentation only.** Simulated backend and offline video only; no hardware.

**Revised CONOPS:**
- the robot places with a prescribed variation, releases, retreats and the element settles;
- the participant reassesses;
- Intervene → recovery (the facilitator may review, assist or reject) → secure grasp at the adjustment position → individual bounded translation and **rotation** nudges → **Place and release** → reassessment, repeatable;
- the final Allow is possible only with the element released.

It is specified in [CONOPS](../docs/plans/Phase2_Task07_S3_1_Revised_CONOPS.md), with open decisions C1–C7 (Retry semantics, the reference frame, the rotational axis convention, the facilitator procedure, the recovery allowance, the live visibility prerequisites, whether to show the cycle).

**Built:**
- schema v1.2: an `element_state` message, kinds `recover` / `place_release` / `repeat_placement`, stages `facilitator_review` / `facilitator_assist`, and the axis `rotation`;
- the released workflow in the S1 machine and simulated backend, with hidden ground truth (variation, settle placeholder, re-grasp) kept backend-only;
- `cdp_summary`, which separates participant decision time from technical, facilitator and paused time;
- a minimally revised Adjust wing.

**The S3 held-element workflow stays selectable,** so every earlier test remains a regression.

**Results:**

| Suite | Result |
|---|---|
| EditMode | 146/146 (20 new) |
| PlayMode | 4/4 |
| S3.1 player session | 39/39 |
| S3 player session | 63/63 |
| `verify_s3_run.py` | PASS |
| M1 and S2 Windows players | 2/2 and 2/2 |
| On-screen plate at 1× | exact |

**C09** was regenerated after another reboot (old reference preserved): `unity/Phase2Client/test_results/c09_boot_session_20261112/`.

**Report:** [S3.1 results](../docs/plans/Phase2_Task07_S3_1_Implementation_Results.md).

**Git:** the researcher accepted S3.1 as the functional baseline (12 Nov 2026), with provisional decisions C1–C7 (CONOPS §11; Retry repeats the programmed placement including its variation; corrections are relative to the programmed pose pending commissioning; 3 recoveries, configurable; the video override is not permission for blind physical operation; cycle and attempt identifiers preserved in the logs). The leak-test scope is clarified: physical construction-state differences are stimuli, not leaks. **Committed as `b5722b82ef79bfb0748a6d29a4fde30a7a381f24`** (local `master`, no remote).

**Next:** S4 is not started and needs approval. Deferred UI refinements are listed in CONOPS §11.

Do not begin S4, Quest, digital twin, machine vision or robot integration without approval.

### 13.23 Task 07 S4.1: experimental configuration and session orchestration, implemented, verified, accepted and committed (12 Nov 2026; offline)

**Simulation only:** simulated backend and offline video; no hardware.

**Specification:** [S4.1 experimental development specification](../docs/plans/Phase2_Task07_S4_1_Experimental_Development_Specification.md). It separates the agreed design, provisional parameters, commissioning items, instrument and scoring items, and discrepancies D1–D10. It includes the researcher's **methodology V17 corrections**:
- 20 analysable participants, up to 24 recruited (5 or 6 per Williams sequence);
- Survey B (8 items) as the block-end instrument;
- architecture-specific SAGAT banks (placeholder content);
- the five architectural-state ground-truth categories, with acceptability and evidence availability kept separate;
- H2 defined by the first substantive commitment;
- the input method (V17: speech recognition) still under review.

**Built** (`unity/Phase2Client/Assets/Phase2/Experiment/Session/`, `Protocols/`, the Site Window session mode, `Builds/S4/SiteWindowSession.exe`):
- a versioned, validated experiment definition with a content ID;
- the W1–W4 allocation register;
- the session runner: training and competency, blocks, trial reset with A and B readiness, two active and one inactive CDP per trial, the formal-CDP observation, SAGAT freeze and restore, the first-commitment lock with confidence, unscheduled holds at the next safe state (merged into a formal CDP when they coincide), facilitator roles A and B with scoped adjustment authorisation, interruptions, measure-level validity, replacement trials, and append-only records with restart reconciliation;
- schema v1.3 (additive only).

**Results:**

| Suite | Result |
|---|---|
| EditMode | 181/181 (35 new) |
| PlayMode | 5/5 |
| S4 player, scripted demonstration | 24/24; `verify_s4_session.py` 23/23 |
| Accelerated full session | 24 formal CDPs, 12 inactive, 12 probes, 24 confidence ratings over 12 completed slots (2 by replacement, one after a simulated application restart); `--full` 26/26 |
| S3 / S3.1 players | 63/63 and 39/39 |
| S2 / M1 players | 2/2 and 2/2 |

No acceptance threshold was changed.

**Report:** [S4.1 results](../docs/plans/Phase2_Task07_S4_1_Implementation_Results.md).

**Git:** the researcher accepted S4.1 after manual review as the **simulated functional baseline**; minor UI design issues are deferred to the later polish stage. **Committed as `6c7e33c9b4ddeb920a9a056a3d169155c4cc40eb`** (local `master`, not pushed; working tree clean).
- **Still open:** the methodological questions (spec §7, D1–D10), the demonstration parameters and the commissioning limitations.
- **S4.2 has not started.**

**Next:** see §13.24 (concurrent Wi-Fi and Ethernet check; live Camera A). Do not begin S4.2, Quest 3, digital twin, machine vision or robot integration without approval.

### 13.24 Concurrent Wi-Fi and Ethernet works; first live Camera A preview with Wi-Fi up passes (12 Nov 2026, 18:15–18:55)

**The university approval was researcher-reported, so I checked it directly; nothing was changed.**

**Policy:** `HKLM\SOFTWARE\Policies\Microsoft\Windows\WcmSvc\GroupPolicy` now has `fMinimizeConnections = 0` and `fBlockNonDomain = 0`. §5 recorded `fMinimizeConnections = 3` ("Prevent Wi-Fi when on Ethernet").

**Adapters, addresses and routes, with the dock link up:**

| Interface | State | Address | Profile | Route |
|---|---|---|---|---|
| WiFi | Up | `10.12.58.66/18` | DomainAuthenticated, Internet | the only default route (via `10.12.63.254`) |
| Ethernet 4 (dock) | Up, 1 Gbps | `169.254.80.246/16` (Preferred) | Public, LocalNetwork | the only `169.254.0.0/16` route |

- Automatic metrics, unchanged: Ethernet 4 = 25, Wi-Fi = 45.
- No overlap and no duplicate address. The disconnected Bluetooth and Wi-Fi Direct adapters hold only tentative APIPA addresses, with no routes.

**Routes actually used (`Find-NetRoute`):**
- the cameras → Ethernet 4, source `169.254.80.246`;
- `8.8.8.8` and `www.adelaide.edu.au` → Wi-Fi, source `10.12.58.66`.

**Same-period test (18:15:08–18:15:37):**
- Camera A ping: **40/40** (≤ 1 ms; ARP at the recorded Camera A MAC `44-A9-2C-32-3C-AC`).
- HTTPS over Wi-Fi: **5/5** (university site 200, generate_204 204). All port-443 connections came from the Wi-Fi address.
- Wi-Fi stayed connected and domain-authenticated throughout.
- Camera B did not reply; it was not connected.

**Result: PASS.** Concurrent Wi-Fi and Ethernet works on this laptop.
- **Remaining restriction:** none observed at the OS level.
- **Not shown:** Roseworthy–North Terrace connectivity.

**Evidence:** `camera_gateway/results/netcheck_concurrent_20261112_181504/` (README, `state.txt`, `web.txt`, `camera_a_pings.csv`).

**Our own isolation guard (not university policy)** assumed Wi-Fi is off:
- `camera_gateway_a.py` refused any non-link-local host address unless the "not to be used" `--allow-non-isolated` was given;
- `tools/run_stage2.ps1` waited for every IPv4 address to be link-local;
- broadcast discovery was guarded (the Luxonis multi-interface issue; with Wi-Fi up it would also broadcast onto the university network).

**The researcher approved** a scoped, opt-in change, and the validated `isolated` path remains the default:
- `camera_gateway/network_scope.py` (read-only check) and `camera_gateway_a.py --network-scope ethernet_scoped`:
  - before any contact, the camera route must use one wired, link-local-only interface with no default route, no other link-local interface, no overlapping subnet, and ARP showing the recorded Camera A MAC;
  - unicast connection only, with no broadcast discovery; then the same ID, IP and bootloader checks, calibration before, during and after the run, IR off and AutoCalibration OFF;
  - the scope is re-checked every 5 s, and any change stops the run.
- `run_stage2.ps1 -NetworkScope EthernetScoped`:
  - waits for the scope check (stable 15 s) and re-checks it during the run;
  - logs a Wi-Fi HTTPS probe every 5 s.
- `analyse_stage2.py`: a labelled S1 `ethernet_scoped` variant. The ARP check and the verified unicast connect replace the broadcast bootloader-state sub-item; every other criterion is unchanged.

**Offline verification:**
- the new `tests/test_network_scope.py` passes 31/31;
- the existing gateway 74/74, Stage 2 analysis 23/23 and continuity 20/20 all pass;
- the plan-only run and the dry run (fakes) were OK;
- pre-change copies are in `camera_gateway/results/*.pre_scope_20261112.bak`.

**Live preview** (`camera_gateway/results/stage2_runner_20261112_183708/`, 18:37; Camera A only, 60 s Unity display; validated keyint 20, `resync`, 150 ms age guard, crop unchanged):
- **S1–S11 all PASS,** including the oracle replay (S10). The gateway exited 0 and Unity exited 0; there were no deviations.
- **Calibration** was unchanged before, during and after the run.
- **Connection:** unicast connect in 8.1 s; both eyes streaming after 17.6 s; 0 link downs; 0 connect failures.
- **Pairing:** 1,537 pairs, 0 skew violations (max 0.031 ms); 20.05 fps.
- **Latency, capture to Unity selection:** median 92.2 ms, p95 92.5, max 109.4. Every displayed pair was fresh, with strictly increasing seq.
- **Wi-Fi during streaming:** **19/19 HTTPS 200** (max 203 ms), all via Wi-Fi. The scope was re-checked 14 times by the runner and 9 times by the gateway monitor, with no change.
- **Freezes:** **one display freeze of 1.1 s** (displayed seq 740). It followed a left-eye stale resync at seq 721, a frame-age jump to 281 ms, which is the documented single-connection RTSP write-stall / GOP-loss pattern (Stage 2: 6 freezes, right eye). Two more left-eye resyncs (seq 1461 and 1485) came after the Unity window. There was no evidence that Wi-Fi caused or worsened them; the stall is on the gateway → MediaMTX localhost connection.
- **Not exercised:** reconnection (no link loss occurred; no fault was injected).
- **Not shown:** Roseworthy–North Terrace connectivity.

**Clock reference:** C09 was regenerated after the 17:46 reboot, with the old file preserved in `unity/Phase2Client/test_results/c09_boot_session_20261112b/`.

**Site Window live source (approved preparation; not committed; not yet run live):**
- **The option:** `S3Session -s3AMode rtsp -s3AServer rtsp://127.0.0.1:8554` switches **Camera A only** to the live stream. It accepts only a localhost server; Camera B stays the labelled synthetic recording.
- **What the participant sees:** the participant tag becomes "SIMULATED ROBOT · LIVE WRIST CAMERA".
- **What is recorded:** `video_sources` with every S3 and S4 run (live Camera A, simulated Camera B, simulated robot; live imagery does not respond to simulated recovery or nudges).
- **Verification (offline):** EditMode 182/182 (one new test); PlayMode 5/5; S4 player script 24/24; S3 63/63 and S3.1 39/39 players. All of these use the offline default.

**Remaining before a live S4.1 session** (to be proposed; needs approval):
1. a runner mode that launches the S4 player instead of the M1 player, with an S4-appropriate analysis: gateway-side S1–S5 and S11, `verify_s4_session.py`, and the oracle replay of the live Camera A receiver folders;
2. either a ≤ 120 s live-smoke protocol, or approval to raise the gateway's 120 s preview-scale cap for the demonstration's length (about 5 min).

### 13.25 Restart point (end of 12 Nov 2026; work stopped at the researcher's request)

**Git** (`unity/Phase2Client`, local `master`, not pushed; working tree clean):

| Commit | Content |
|---|---|
| `ca5c80334ca3b4bf3083216a9ad842431d6562c6` | Development checkpoint: the Camera A live-source option. Offline regressions passed; **live S4.1 integration not yet tested** |
| `6c7e33c9b4ddeb920a9a056a3d169155c4cc40eb` | S4.1, accepted, unchanged |
| `b5722b8` | S3.1 |
| `e418f62` | S3 |

**Outside Git** (`camera_gateway/` and the docs are not Git repositories): the network-guard change and its documentation are backed up in `backups/20261112_live_camera_restart/`, with a `MANIFEST.md` (SHA-256 of every file) and restoration instructions.

**State:**
- **Connectivity:** concurrent Wi-Fi and Ethernet is **verified** (§13.24).
- **Preview:** the 60 s live Camera A preview (`ethernet_scoped`) **passed** the integrity checks S1–S11, with Wi-Fi usable during streaming.
- **Still unresolved:** **one 1.1 s freeze**, the known single-connection RTSP write-stall / GOP-loss pattern.
- **Still untested:** **reconnection** (no link loss occurred) and **inter-site (Roseworthy–North Terrace) connectivity**.
- **Live S4.1 has not run.**
- **Processes:** the test processes were checked after the run; the camera connection was closed by the gateway's normal shutdown.

**Next task (needs approval):**
1. an **S4-compatible live runner**: the Stage 2 runner launching the S4 player with `-s3AMode rtsp`, and an S4-appropriate analysis (gateway S1–S5 and S11, `verify_s4_session.py`, the oracle replay of the live Camera A receiver folders);
2. **a decision about test duration**: a ≤ 120 s live-smoke protocol, or approval to raise the gateway's 120 s preview-scale cap.

Do not run further live tests, raise the cap, or change the runner before that approval.

**After any reboot,** recheck the clock reference with the existing procedure before trusting EditMode C09:
1. run the EditMode suite;
2. if C09 reports a STALE reference, keep the old `test_results/inputs/clock_reference.json` in a dated `test_results/c09_boot_session_<date>/` folder;
3. run `..\..\streaming_poc\.venv\Scripts\python.exe -I Tools\make_clock_reference.py` in `unity/Phase2Client`;
4. rerun EditMode and record the before and after results in that folder (examples: `c09_boot_session_20261112b/`).

### 13.26 Live S4.1 smoke test with live Camera A: PASS (13 Nov 2026, 12:35–12:38; approved; Unity changes later committed as `807ef39`, see §13.27)

**Restart checks:**
- **Commits:** `ca5c803`, `6c7e33c` and `b5722b8` are present; the tree was clean.
- **Backup:** all 34 manifest files match, both the backup copies and the files in place.
- **C09:** stale after the 11:24 reboot (EditMode 180/182). Preserved and regenerated, then EditMode 182/182. Evidence: `unity/Phase2Client/test_results/c09_boot_session_20261113/`.
- **Network:** the policy is still `fMinimizeConnections = 0`. The dock was disconnected at first; the researcher reconnected it.

**Camera identity incident (guard worked):** after the dock was reconnected, **both** `169.254.1.222` and `.223` resolved to **Camera B's MAC** `44-A9-2C-37-BA-5D`, the §6.4 anomaly with both cameras attached.
- The scoped guard refused, and nothing was contacted beyond ping and ARP.
- The researcher then unplugged Camera B. After that, `.222` resolved to Camera A's MAC `44-A9-2C-32-3C-AC` and the scope check passed.
- **Evidence:** `camera_gateway/results/netcheck_concurrent_20261113_123057/` (same period: Camera A pings 20/20, HTTPS via Wi-Fi 3/3).
- **Lesson:** run live tests with **only Camera A** on the switch.

**Built** (uncommitted; minimal; the M1 runner path and the offline regressions are preserved):
- `Assets/Phase2/Experiment/Protocols/phase2_s41_live_smoke.json`: a separate, labelled **development smoke-test** definition: 1 block, 1 trial, 3 placements, all on primary Camera A; the probe at the first CDP; shortened timings. The research protocol and the accepted demonstration are unchanged.
- `SiteWindow/Unity/S41LiveSmokeScript.cs` (`-s4LiveSmoke`): real clicks through the coverage below. Without a live Camera A, the live-specific checks are named `…_rehearsal`.
- `S4SessionMode.cs`: when Camera A is live, the restored view must also be current (video Live).
- `S3Session.cs`: the `-s4LiveSmoke` flag.
- `camera_gateway/tools/run_stage2.ps1 -Player S4Smoke` (M1 is still the default). It refuses any `-PreviewSeconds` over 85, so the run fits the **unchanged 120 s gateway limit**.
- `analyse_stage2.py --player s4`: a labelled S6 Site Window variant. S1–S5 and S7–S11 are unchanged.
- Pre-change copies: `camera_gateway/results/*.pre_s4smoke_20261113.bak`.

**Offline checks before the live run:**

| Check | Result |
|---|---|
| EditMode | 183/183 (new: the smoke definition is valid and labelled, and a simulated smoke session takes 16.7 s, well inside the budget) |
| PlayMode | 5/5 |
| Gateway suites | gateway 74, network scope 31, Stage 2 analysis 23, continuity 20 |
| Runner, plan-only | `-PreviewSeconds 90` is refused ("would not fit inside the gateway's 120 s limit"); 85 is accepted |
| Runner, dry runs (fakes) | S4Smoke and M1 both OK |
| S4 player, offline rehearsal | everything passes except, by design, `source_declared_rehearsal`; session verifier 23/23 |

Re-analysing the 12 Nov M1 run with the new script gave identical criteria and measurements, and its original analysis file was restored from the backup.

**Live run** (`camera_gateway/results/stage2_runner_20261113_123525/`):
- **Configuration:** EthernetScoped, S4Smoke, validated keyint 20, `resync`, 150 ms age guard, crop unchanged.
- **Integrity: S1–S11 all PASS,** including the S6 Site Window variant and the S10 oracle replay (1,221 ops, 0 mismatches).
- **Gateway and player:** the gateway exited 0 and the player 0, with no runner deviations. The gateway streamed for about 48 s of its 120 s limit; both eyes were up 18.2 s after it started. The player ran for 24.4 s, and the session took 16.3 s.
- **Calibration** was unchanged before, during and after the run.

**Coverage achieved** (16/16 smoke checks pass):

| Coverage | Smoke check |
|---|---|
| Live Camera A in the Site Window | `smoke_live_camera_A_in_site_window` |
| Probe hides the imagery | `smoke_probe_hides_imagery` |
| Current live view restored after the probe (`view_restored` before `decision_ready`; no restore timeout) | `smoke_current_live_view_restored_after_probe` |
| Inspect → synthetic Camera B (labelled "simulated feed") → Camera A → end Inspect → live primary view at 1× | `smoke_inspect_switch_and_return_to_live_view` |
| First commitment locked; confidence prompt before simulated execution, at both CDPs | `smoke_first_commitment_locked_before_execution`, `smoke_commitment_executes_after_rating` |
| Session closed; integrity pass | `smoke_session_closed`, `smoke_session_integrity_checks_pass` |

`verify_s4_session.py` passes 23/23.

**Video and connectivity:**
- **Freezes:** **none**. The largest interval between displayed Camera A pairs was 99.8 ms.
- **Freshness:** all 229 displayed pairs were fresh, within the absolute-age limit, in strictly increasing seq, with 0 integrity errors.
- **Pairing:** 603 gateway pairs, 0 skew violations (max 0.032 ms), 20.1 fps.
- **Latency, capture to selection:** median 91.3 ms, p95 99.7, max 131.6.
- **Resyncs:** only the known start-up stall (seq 0, 199 ms, one GOP resync per eye). There were **no** mid-stream resyncs and no link losses.
- **Wi-Fi during streaming:** **10/10** HTTPS 200 via Wi-Fi. The scope was checked 9 times by the runner and 3 times by the gateway monitor, with no change.
- **Cleanup:** nothing left running, port 8554 closed, no new crash dumps, no TCP connection to the camera.

**Source identities** (recorded in `presentation_started` and `video_prepared`):
- Camera A: **live**, via the gateway and localhost MediaMTX.
- Camera B: **SIMULATED** (the synthetic recording; not exhausted).
- Robot: **SIMULATED**; the live imagery does not respond to the simulated actions.

The end of stream was planned in every case: the gateway's stop file and the receiver's `s3_script_done`. No failure ended a source.

**Evidence:**
- runner folder (gateway, analysis, Wi-Fi probe, receivers);
- session records under `s4_sessions/S4-P901-01/`;
- the player's interface log and screenshots in `unity/Phase2Client/test_results/ai2_s4_20261113_123628_win64player/`.

**Still open:**
- the 12 Nov 1.1 s freeze (not reproduced in this short run);
- reconnection behaviour;
- inter-site connectivity;
- longer live sessions, which would need a duration decision;
- the S4.1 methodology questions D1–D10.

**Not committed (for review):**
- Unity repository: `S3Session.cs`, `S4SessionMode.cs`, the new `phase2_s41_live_smoke.json`, `S41LiveSmokeScript.cs` and `LiveSmokeProtocolTests.cs` (plus their `.meta` files);
- `camera_gateway`: `tools/run_stage2.ps1`, `tools/analyse_stage2.py`.

### 13.27 Extended-test mode for the full interactive S4.1 walkthrough: prepared and verified offline (13 Nov 2026; NOT committed; live run in §13.28)

**Smoke-test acceptance (researcher, 13 Nov 2026):** the §13.26 run is accepted as a **development integration milestone** only. It does **not** establish long-duration streaming reliability, dual-camera operation or physical robot readiness.
- **Unity commit:** `807ef39`, containing the smoke files and a Unity README note with the result and its limitations. The tree is clean; nothing pushed.
- **Backup:** `backups/20261113_live_smoke_checkpoint/` (24 files, `MANIFEST.md` with SHA-256 hashes), holding the gateway runner/analyser and external docs. The earlier backup `backups/20261112_live_camera_restart/` and all raw evidence are preserved.

**Purpose:** run the existing, **unchanged** `phase2_s41_interactive_demo.json` (SHA-256 `1bb2e73d…77e7c5`) with live Camera A, synthetic Camera B and a simulated robot, with a person playing the participant. The researcher authorised an explicit, opt-in extended mode: a **hard gateway maximum of 600 s**, and a shorter player deadline that reserves time for start-up and cleanup.

**Built** (uncommitted; `camera_gateway` is not under Git; pre-change copies are in `camera_gateway/results/*.pre_extended_20261113.bak`):

`camera_gateway_a.py --extended-test`
- `--seconds` may go up to `EXTENDED_MAX_S = 600`. Without the flag, the validated 5–120 s limit is unchanged.
- The plan records `duration_limit_s` and `extended_test`.
- Every other safeguard and default is unchanged: Camera A identity, calibration checks, IR off, keyint 20, `resync`, 150 ms age guard, loopback server, and the `ethernet_scoped` ARP/MAC and unicast checks.

`tools/run_stage2.ps1 -Player S4Demo -ExtendedTest -GatewaySeconds G -PreviewSeconds P`
- **Refusals before anything is launched:**
  - `S4Demo` without `-ExtendedTest`;
  - `-ExtendedTest` with M1 or S4Smoke;
  - `G ≠ 120` without `-ExtendedTest`;
  - `G` outside 120–600;
  - `P > G − 75`.
- **Check at player launch:** the player is not launched if `P + 45` exceeds the gateway time actually left. The runner then stops everything cleanly.
- **Player command:** the S4 player with the interactive demo protocol, the facilitator console, auto facilitators, `-s3AMode rtsp`, `-s3Seconds P` and `-s3Quit`. The player ends on window close (Alt+F4) or at the deadline.
- **Analysis:**
  - `analyse_stage2.py --player s4demo --out stage2_analysis_<receiver>.json`, run once per live Camera A receiver (the player restarts its receivers at every trial reset);
  - then `tools/summarise_live_walkthrough.py`.
- **Unchanged:** the M1 default and `-Player S4Smoke`. Their plan commands are identical to the §13.26 run apart from the run-folder name.

`analyse_stage2.py --player s4demo`
- A labelled S6 variant:
  - the live receiver is camera/rtsp, displayed pairs, readers joined;
  - the receiver ended in a planned way (trial reset, or the player's own end);
  - the player ended by window close, deadline or facilitator finish;
  - the session completed with its integrity checks passing.
- S1–S5 and S7–S11 are unchanged.
- `--out` accepts only a plain `.json` file name.

`tools/summarise_live_walkthrough.py` (new) writes `walkthrough_summary.json` and `.md`. It separates **what the participant saw** from **what the stream did**:
- **Visible stalls:** Camera A on screen with no new image for ≥ 125 ms (the receiver's freeze threshold). Each is classed as one of:
  - `trial_start_receiver_restart`: planned, but the wait is visible;
  - `unexpected_visible_interruption`;
  - `end_of_stream_while_visible`.
- **Receiver freezes:** labelled visible, hidden by the planned SAGAT probe, hidden by a Camera B selection, or hidden by a session screen.
- **Render hitches:** the Site Window not redrawn and no screen change.
- **Planned hiding:** SAGAT hide and restore times, plus the age of the image at restore; Camera B selections.
- **Also recorded:** freshness and the capture-to-selection latency distribution (all pairs, and pairs shown on screen); Wi-Fi probe statistics; shutdown and cleanup; duration settings.

**Offline verification** (evidence: `camera_gateway/results/extended_offline_checks_20261113/`):

| Check | Result |
|---|---|
| Gateway suite | 81/81 (new: 121 s refused without the flag; 601 s and 1e9 s refused with it; Camera B and a non-loopback server still refused with it; 600 s accepted only with the flag; every other default unchanged) |
| Network scope / continuity | 31/31, 20/20 |
| Stage 2 analysis | 33/33 (new: the s4demo PASS case, six designed-to-fail cases, and `--out` path refusal) |
| Walkthrough summariser | 20/20 on a synthetic two-trial run with known events (one of each class) |
| Runner, plan only | 13/13 cases as expected: 10 refusals (601, 100000, below 120, the 75 s reserve breached, S4Demo without the flag, the flag with M1 or S4Smoke, 121 s on M1, S4Smoke 90 s still refused); 3 accepted (S4Demo 600/525 carries `--seconds 600 --extended-test` and the interactive protocol; S4Smoke 85 and M1 unchanged) |
| Runner, dry runs (fakes) | S4Demo 150/20 completed and clean. `late_player`: refused at launch, player not started, clean. `gateway_abort`: player not started, clean. Hung player: stopped at P + 45 s, clean. M1 and S4Smoke regressions completed. |
| Real S4 player, offline (synthetic cameras), 20 s deadline | `max_seconds` at 20.03 s, exit 0, 27.5 s wall time; the session recorded `application_closing` (resumable) |

**Finding from re-summarising the §13.26 smoke run** (a copy; the evidence is unchanged):
- When the trial view opened, Camera A was on screen for **1.54 s before its first image**. The participant-facing label read "interrupted" for 1.03 s of this.
- **Cause:** the player restarts its receivers at each trial reset, and RTSP reconnection plus GOP sync takes about 2 s.
- **Why it was missed:** the §13.26 "no freezes" result counts receiver freezes after the first displayed pair, so this wait was not counted.
- **Expected in the full demo:** the wait will recur at every trial start. It is now reported as a planned-restart wait, separately from unexpected interruptions.
- **Also found:** one 161 ms render hitch, on the first Site Window frame inside that wait.
- **No change made:** nothing was changed to hide or shorten this, in line with the no-UI-redesign constraint.

**Recommended live settings:**
- `-GatewaySeconds 600 -PreviewSeconds 525`, which gives the player 525 s.
- Earlier human-paced demo runs (12 Nov) took 379 s (completed) and 327 s (quit mid-trial).
- If the deadline is reached, the session is not completed, S6 records FAIL, and the session can be resumed.

**Hardware:**
- Only **Camera A** is on the PoE switch.
- **The dual-camera address/MAC anomaly (§6.4, §13.26) is UNRESOLVED.** The scoped guard is not bypassed.

**Not done in this task:**
- no encoder changes;
- no injected link failures;
- no robot integration;
- S4.2 not started;
- no UI redesign;
- nothing committed.

### 13.28 Live full interactive S4.1 walkthrough, live Camera A: completed; session and integrity PASS, but 11 unexpected visible freezes (13 Nov 2026, 15:06–15:14; NOT committed)

**Run:**
- **Command:** `run_stage2.ps1 -NetworkScope EthernetScoped -Player S4Demo -ExtendedTest -GatewaySeconds 600 -PreviewSeconds 525`.
- **Folders:** runner `camera_gateway/results/stage2_runner_20261113_150631/`; gateway `results/gw_20261113_150707_A_stage2/`.
- **Pre-flight:** the laptop had not rebooted since 11:24, before §13.26, so C09 still applied. No leftover processes; port 8554 free. `.222` resolved to Camera A's MAC; `.223` did not answer (Camera B unplugged).
- **Participant:** played by the researcher (P901, session `S4-P901-01`). Facilitators were automatic; Camera B synthetic; robot simulated.
- **End:** the researcher pressed Alt+F4 on the completion screen at 337.4 s (`application_quit`). The 525 s deadline was not reached.

**Results:**

| Item | Result |
|---|---|
| Session | completed, integrity pass |
| Stage 2 analyses (one per live receiver; 3 trial resets) | 3/3 PASS, S1–S11 all PASS |
| Gateway | PASS; streaming after 16.9 s; 583.1 s left at player launch; stop by stop file; calibration unchanged (before, in session, after); errors 0 |
| Freshness | 5616/5616 displayed pairs fresh and within the absolute limit (1707/1707 while Camera A was on screen) |
| Capture to selection | median 87.8 ms, p95 97.1 ms, p99 103.6 ms, max 136.8 ms; histogram <100: 5495, 100–125: 120, 125–150: 1, ≥150: 0 |
| Planned hiding | 3 SAGAT probes (hidden 5.1 s, 3.0 s, 3.3 s), all restored in 25–36 ms with image age 6–9 ms at restore; 6 Camera B selections (171 s in total) |
| Trial-start wait (planned receiver restart, visible) | 1 counted, 514 ms showing "interrupted". The other two restarts finished behind session screens (first image after 735 ms and 1171 ms). |
| **Unexpected visible interruptions** (Camera A on screen, mid-stream) | **11** in 93 s of Camera A on screen (8 segments): 252–1048 ms visible (median 749 ms); 8 long enough to show "interrupted" |
| Receiver freezes (stream level) | 28 in total: 13 while Camera A was visible; 13 hidden behind a Camera B selection (longest 2313 ms); 2 behind session screens |
| Render hitches | 1, 170 ms, inside the first trial-start wait |
| Wi-Fi (HTTPS every 5 s) | 73/73 HTTP 200; median 92 ms, max 206 ms; longest gap between successes 6.3 s |
| Network scope | 45 checks (40 while streaming); no failure |
| Shutdown | runner `completed`, no deviations; player exit 0; gateway exit 0; MediaMTX stopped; no processes left; port 8554 free; no new crash dumps |

**Cause of the freezes (diagnosis, read-only):** they come from the gateway's 150 ms age guard and `resync` policy, triggered by stalls in the **host-side RTSP write**. They are not camera, network or Wi-Fi faults. Evidence is in `results/walkthrough_diagnostics_20261113/`.
- **The camera delivered on time.** `device_gaps` 0; capture rate 20.01 fps. Camera-to-host arrival: median 73 ms, max 205 ms, only 6 of 14,234 frames over 150 ms.
- **The gateway dropped stale frames.** It made 31 mid-stream `gop_resync` (reason `stale`) events, each for **one eye only**, with frame ages of 225–337 ms. That is 16 for the left eye and 17 for the right (`skipped_stale`), discarding 139 and 174 frames until the next keyframe.
- **The write stalled** (refined in §13.30: the hold starts *after* earlier frames were handed to the socket). In every case, the `out.write` (PyAV mux to localhost MediaMTX) for the frame sent just before the resync took **249–360 ms (median 303 ms)**, against the usual 50 ms. The other eye kept sending normally in the same window (5 frames per 250 ms). The next queued frame was then over 150 ms old, so the queue was discarded up to the next keyframe. That turns a ≈ 0.3 s write stall into a 0.5–1.25 s freeze.
- **Ruled out: Wi-Fi probe timing.** Only 6/31 stalls fell within ±1 s of a probe, which is about chance.
- **Known issue, not new:** this is the ≈ 300 ms loopback RTSP write stall already seen in the 6 Nov Stage 2 preview (§13.19: 210–316 ms blocked writes, one eye at a time). The continuity investigation analysed it (hypothesis: loopback TCP retransmission timeout, unproven). It recommended `-Keyint 10` (freezes about 30 % shorter in simulation), which has not been adopted. What makes the write block is still unproven. Stalls started 68 s after the gateway started, about 20 s into the first trial, and recurred about every 11 s (median) until the end. The §13.26 smoke run had none mid-stream; its only resync was at start-up. *Correction (§13.30):* 85 s was that run's player deadline. It actually streamed for 29.1 s, and Camera A was received for 13.6 s and visible for 12.0 s.
- **Also the likely mechanism** of the open 12 Nov 1.1 s freeze. This run shows its rate under the full interactive load: about one freeze every 8.5 s of Camera A viewing.
- **Not changed:** nothing here was altered (encoder, keyint, age guard or stale policy), as required.

**Shutdown note (pre-existing):** after the stop, depthai logged "Device crashed, but no crash dump could be extracted". The post-run calibration read needed 2 connection attempts (72 s wait) and then matched. The same messages and the same 72 s wait also occurred in the §13.26 smoke run and the 12 Nov run. *Correction (13 Nov, after review):* recurrence alone does not show that this is expected behaviour, so it is recorded as open issue **O2** in §13.29. The optional bootloader-update warning was ignored; no firmware changes.

**Assessment:**
- **Demonstrated:** the full interactive S4.1 protocol runs end to end with live Camera A, synthetic Camera B and the simulated robot, for 5.6 min. Freshness held for every displayed pair. Planned SAGAT hiding and restore and Camera B switching worked. The 600 s limit and the player deadline were respected, and cleanup was complete.
- **Not established:** smooth live video. The participant saw 11 unexpected freezes (mostly 0.5–1.0 s) in 93 s of Camera A on screen, about one every 8.5 s.
- **Also not established:** long-duration reliability, dual-camera operation, inter-site connectivity and robot readiness.

**Next step (researcher decision; not started):** the options from the continuity investigation still stand: `-Keyint 10`, a longer age limit or `catchup`, or a loopback investigation. A bounded, read-only diagnosis (timing each `write` against MediaMTX reader state and host load) would help choose between them. No change has been made.

### 13.29 Researcher acceptance of the live walkthrough, with open issues recorded separately (13 Nov 2026)

**Accepted milestone: functional integration (researcher, 13 Nov 2026).** The §13.28 run is accepted as a **functional integration milestone**.
- **What it shows:** the full interactive S4.1 protocol, with live Camera A, synthetic Camera B and a simulated robot, ran end to end with a person as participant.
  - The session completed with integrity checks passing.
  - All 3 per-receiver Stage 2 analyses passed, and every displayed pair was fresh.
  - SAGAT hiding and restore, and Camera B switching, worked.
  - The duration limits and cleanup behaved as designed.
- **Manual review:** the researcher found no major workflow problems. UI refinement stays deferred.
- **What it does not establish:** streaming continuity, long-duration reliability, dual-camera operation, inter-site connectivity or physical robot readiness.
- **Evidence:** `camera_gateway/results/stage2_runner_20261113_150631/` (with `walkthrough_summary.md`) and `results/gw_20261113_150707_A_stage2/`.

**Open issues** (not accepted; tracked separately from the milestone):

| ID | Issue | Status |
|---|---|---|
| **O1** | **Streaming continuity:** 11 unexpected visible freezes (252–1048 ms) in 93 s of Camera A on screen. They followed per-eye gaps of ≈ 300 ms between gateway sends, which tripped the 150 ms age guard and resync. | **Not accepted.** Under diagnosis (§13.30). Keyframe interval, encoder settings, the 150 ms limit and the resync policy are unchanged. |
| **O2** | **Camera shutdown anomaly:** after every live gateway stop, depthai logs "Device crashed, but no crash dump could be extracted", and the post-run calibration read needs a second connection after about 72 s. | **Unresolved.** Recurrence is documented; the cause is not established (§13.30). |
| O3 | **Dual-camera address/MAC anomaly** (§6.4, §13.26) | Unresolved. Live tests run with Camera A only; the guard is not bypassed. |

**Extended-mode code:** still uncommitted (`camera_gateway` is outside Git). It is preserved in `backups/20261113_extended_walkthrough_checkpoint/` with a SHA-256 manifest.

**Unity:** unchanged at `807ef39`. That commit contains only the §13.26 smoke-test milestone:
- `phase2_s41_live_smoke.json`;
- `LiveSmokeProtocolTests.cs`;
- `S41LiveSmokeScript.cs`;
- small `S3Session.cs` and `S4SessionMode.cs` hooks;
- the Unity README note.

### 13.30 Diagnosis of O1 (gateway write stalls) and O2 (shutdown anomaly) from existing logs (13 Nov 2026; read-only; nothing changed)

**Scope:** existing logs only, plus new read-only scripts.
- **Unchanged:** keyframe interval, encoder settings, the 150 ms freshness limit, the resync policy, the gateway, the runner and Unity.
- **Evidence:** scripts and outputs in `camera_gateway/results/walkthrough_diagnostics_20261113/` (see its README).
- **Clock:** every log (gateway, session runner, UI, 3 receivers) shares the same host monotonic clock to within 0.15 ms (`clock_bases.txt`).

#### O1.1 What is measured directly and what is hypothetical

**Measured directly** (31 mid-stream stale resyncs; 29 with a Unity reader connected, so arrivals can be matched; `o1_chain_and_view.json`):

| Quantity | Result |
|---|---|
| Camera to gateway | On time throughout. No device gaps; capture rate 20.01 fps. During every hold, the gap between frame receipts on either eye was ≤ 53.5 ms. |
| **Hold** (first held frame handed to the socket → that frame's arrival in Unity) | **302–320 ms, median 312 ms** (n = 29). Near-constant. |
| Frames the socket accepted during the hold before the next write blocked | 0 (5 stalls), 1 (12), 2 (12); 37–198 kB (median 94 kB) |
| Blocked write (upper bound) | 203–312 ms, in three clusters (≈ 210 / 260 / 310 ms), i.e. 312 ms minus 50 ms for each frame accepted first |
| Blocked write return vs held data reaching Unity | Within 5 ms (−4.9 to +0.3 ms); the held frames arrive together within ≤ 9.5 ms (one exception, at 191 s) |
| Other eye during each hold | Unaffected: send-to-arrival ≤ 4.9 ms |
| Stalls with no Unity reader connected | 2 (at 360.4 s and 365.0 s, after the last receiver closed at 359.9 s) |
| Blocked frames | Delivered about 300 ms old and **rejected** by Unity's freshness check (14 `pair_rejected`, `excess_delay`). Every *presented* pair was fresh. |
| MediaMTX log | No warnings. The only note is the start-up "RTP packets are too big (1460 > 1440), remuxing", on both paths. |
| Stall rate | 29 in 308 s with a reader connected (≈ 1 per 10.6 s); 0 in about 39 s of streaming before the first reader; 2 in the 8.6 s after the readers closed, while the player was quitting |

**Inferred, not measured:**
- That the blocked write waits on a full socket send buffer. This is standard blocking-socket behaviour and fits the 37–198 kB accepted first, but no per-write start time or socket state was logged.

**Hypothetical:**
- What creates the hold.
- The Windows minimum retransmission timeout (documented default 300 ms). The local MIB counter reports `RtoMin` = 5 (`tcp_counters_probe.txt`), so this value is unverified.

**Correction:** my earlier note that this run "differs from the 6 Nov pattern" came from a bug in my first script, which never found held frames. It was corrected before reporting. The pattern is the same as 6 Nov (§13.19): data handed over normally, held for about 310 ms, then a blocked write.

#### O1.2 Where the delay sits (gateway publishing → MediaMTX → Unity reception)

- **Not the camera, the capture thread or the gateway process as a whole:** capture continued, and the other eye's sender ran normally during every hold.
- **Not Unity reception:**
  - the other eye was delivered normally within the same hold;
  - holds occurred with no reader connected;
  - a reader-side hold would not back up into the gateway's write, because MediaMTX gives each reader its own queue. That is MediaMTX's design; not verified here.
- **Located:** after the gateway's socket accepted the data, and upstream of MediaMTX's fan-out to readers. That means the gateway → MediaMTX loopback TCP connection for one path, or MediaMTX's reading of it.
- **Backpressure:** the blocked write is backpressure from that held connection, not from MediaMTX's readers or Unity.

| Candidate | Fit with the measurements |
|---|---|
| **H1: a lost segment on the loopback TCP connection, recovered at the retransmission timeout** | **Best fit.** It explains a near-constant ≈ 310 ms hold; one connection at a time; data accepted until the buffer fills, then the write blocks; the held data released as a burst. The 6 Nov G1 runs, with a different publisher (libx264) on the same machine, showed the same quantum. **Not yet tested:** no retransmission count was recorded, and the timeout value is unverified. |
| H2: MediaMTX stops reading one publisher connection | Would also hold data and block the write. However, a Go scheduling or read pause would vary in length rather than sit at 302–320 ms, and nothing is logged. **Disfavoured, not excluded.** |
| H3: host scheduling or CPU starvation | A process-wide or host-wide pause is **excluded** (capture and the other eye continued). A pause specific to one MediaMTX goroutine is H2. |
| H4: a fixed-timeout inspection of loopback traffic by security or filter software on this managed laptop | Could give a constant hold. **Untested; not excluded.** |
| H5: Unity scheduling or reader backpressure | **Excluded** as the origin (see above). |

**Unexplained:** why holds are frequent with a reader connected but absent in the 39 s before the first reader. This is suggestive only (P ≈ 0.02 at the connected rate).

#### O1.3 What the participant saw (10 freezes fully on screen; `o1_chain_and_view.json` part B)

Site Window code (`S3Session.Condition`, `SiteWindowUi`):
- **Up to 500 ms without a new image:** the plate keeps the last image at full brightness with the normal "Live" caption.
- **After 500 ms:** an amber frame and "Video interrupted · x.x s". The image is **not dimmed**; dimming is used only for "waiting" and "unavailable".

| Measure | 10 visible freezes |
|---|---|
| Time with no new image | 466–1048 ms (median 757 ms) |
| "Video interrupted" shown | in 8 of 10, from 515–516 ms after the last new image, for 84–532 ms |
| Freezes with no visible indication | 2 (466 ms each): a frozen image labelled "Live" |
| **Age at presentation** of the last image before the freeze | 79–90 ms (fresh) |
| Age at presentation of the next image | 85–105 ms (fresh) |
| **Age of the image left on screen** when it was finally replaced | **546–1138 ms (median 845 ms)** |
| Planned hiding | SAGAT probes (3) and Camera B selections are separate and not counted here |

**Freshness at presentation held throughout. The on-screen image did not stay fresh:** it was up to 1.14 s old, and for its first 500 ms it was labelled "Live".

#### O1.4 Trial-start readiness and the formal observation interval

- **The trial-start gate does not wait for a valid image (code defect, not changed).**
  - `TrialReset` requires `video_ready` = `FeedA.Ready && FeedB.Ready`, where `Ready` = `Uploads > 0`.
  - A new receiver allocates a zero-filled image buffer and sets its size at start-up, with `PairsCopied = 0`. `CameraFeed` starts with `_seen = -1`, so its first `Poll` uploads that empty buffer as a "pair".
  - The result is that `Ready` becomes true 14–58 ms after each receiver restart, with no camera image. The state reads "live" and then "interrupted" after 500 ms, and the plate shows the zero buffer (black, inferred from code) instead of the "waiting" veil.
- **This run:** the runner's 1.5 s facilitator auto-confirm delay hid the defect in trials 2 and 3, where the first real image came at 1.23–1.51 s. In trial 1 (practice), the first real image came at 2.03 s, so the Site Window showed for **514 ms with no camera image** and "Video interrupted". With faster manual confirmations, a trial could start on the empty placeholder.
- **Same gate logic** exists in `S3Session.StartTrialWhenVideoReady`.
- **Formal observation intervals** (3 s each; 6 in this run) do not check or record video continuity:
  - `observation_begin` and `observation_end` carry no video fields;
  - `sagat_freeze` records only the instantaneous state.
- **In this run:** one of the 2 observation intervals with Camera A on screen (B1-T1 early, 170.03–173.03 s) began 63 ms into a 765 ms freeze, with "Video interrupted" visible for its last ≈ 250 ms. The following `sagat_freeze` recorded `video_state: live`. Nothing in the session data flags this interval.

#### O1.5 Smoke-test intervals reconciled (`intervals_smoke_vs_walkthrough.txt`)

| Interval | §13.26 smoke | §13.28 walkthrough |
|---|---|---|
| Player deadline (`-PreviewSeconds`) | 85 s | 525 s |
| Gateway process (start → end, including the post-run calibration read) | 115.3 s | 443.3 s |
| Gateway streaming (first RTSP link → stop file) | 29.1 s | 354.8 s |
| Player wall time (launch → exit) | 24.4 s | 348.8 s |
| Session elapsed (player's own record) | 16.3 s | 337.4 s |
| Camera A receiver connected | 13.6 s (1 receiver) | 308.1 s (3 receivers) |
| **Camera A visible on screen** | **12.0 s** | **93.0 s** |
| Mid-stream stale resyncs | 0 | 31 (29 with a receiver connected) |

**Meaning:**
- "85 s" in §13.26 and the `807ef39` commit message was the deadline, not the duration.
- At the walkthrough's rate, 0 stalls in 13.6 s of reception has a probability of about 0.28.
- The smoke test's "no freezes" therefore says nothing about continuity.

#### O2 Camera shutdown anomaly (`o2_shutdown_runs.txt`; still unresolved)

| Live run | Network mode | Post-run reconnect | "Device crashed" lines | Calibration |
|---|---|---|---|---|
| 6 Nov Stage 1 | isolated | waited 8.5 s | none recorded | unchanged |
| 6 Nov Stage 2 | isolated | waited 13.3 s | 0 | unchanged |
| 12 Nov Stage 2 | ethernet_scoped | 2 attempts, 72.07 s, first ends with `io error` | 1, 58.7 s after the stop | unchanged |
| 13 Nov smoke | ethernet_scoped | 2 attempts, 72.16 s, `io error` | 1, 56.8 s after the stop | unchanged |
| 13 Nov walkthrough | ethernet_scoped | 2 attempts, 72.21 s, `io error` | 1, 59.1 s after the stop | unchanged |

- **When it occurs:** the message comes from the **post-run verification reconnect**, about 57–59 s after the stream stopped. It does not occur at the stream close itself.
- **Code difference:**
  - the isolated path (`calibration_check.reconnect_and_read`) polls discovery until the camera is back in bootloader state, then connects;
  - the scoped path (`reconnect_unicast_and_read`, added 12 Nov) calls `dai.Device(DeviceInfo(ip))` straight after the close. That first attempt blocks for about 58 s, depthai logs "Device crashed, but no crash dump could be extracted", and the attempt fails. The second attempt connects in 13.5 s.
- **Strongest supported reading:** the first unicast attempt meets the camera while it is still rebooting after the close.
- **Not established:**
  - whether the camera actually crashed (no crash dump; the crash-dump list is unchanged);
  - whether the camera is harmed (calibration is unchanged every time).
- **Status:** the earlier phrase "expected close behaviour" is **withdrawn**. O2 stays open.

#### Strongest supported explanation and the smallest discriminating next test

**Explanation (O1):**
- Roughly every 10 s, one gateway → MediaMTX loopback TCP connection (one eye) holds the data already handed to it for a near-constant ≈ 310 ms.
- The socket accepts 0–2 more frames, then the gateway's write blocks until the hold ends.
- The validated 150 ms age guard and resync policy then drop that eye up to the next keyframe. The participant sees a 0.5–1.05 s freeze of an image that was fresh when presented but up to 1.14 s old by the end.
- **The cause of the hold is not proven.** A lost-segment retransmission timeout (H1) fits best.

**Smallest discriminating next test (needs approval; not started):**

| Item | Proposal |
|---|---|
| **Purpose** | Test H1 directly. If held loopback segments are retransmitted, the system TCP "segments retransmitted" counter should step within a few ms of each hold's release, well above its background rate. |
| **Instrumentation** | A new standalone, read-only sampler. It reads `GetTcpStatisticsEx` (IPv4 RetransSegs, OutSegs) every 10 ms (≈ 10 µs per call; no admin rights; verified readable) and writes `tcp_counters.csv` with host monotonic timestamps. **No change** to the gateway, runner, encoder, age guard or Unity. |
| **For O2 at no extra cost** | A 1 Hz ICMP ping of Camera A (`169.254.1.222` only) from the stop file until the runner's final check. It records when the camera drops off and returns, relative to the first reconnect attempt. |
| **Run** | The existing default `run_stage2.ps1 -NetworkScope EthernetScoped` M1 preview, within the unchanged 120 s gateway limit (no extended mode). Camera A only; Camera B disconnected. About 4 minutes wall time, including the 72 s post-run reconnect. Expected about 8–10 holds (6 per minute on 6 Nov; 1 per 10.6 s here). |
| **Evidence to collect** | The usual runner, gateway and receiver folders, plus `tcp_counters.csv` and `camera_ping.csv`. |
| **Analysis** | Match each hold (from `sent.csv` and `arrivals.csv`) against counter steps; compare with the background step rate in hold-free windows. |
| **Reading** | **H1 supported:** steps coincide with most releases. **H1 disfavoured:** no steps while holds occur (or loopback retransmissions are not counted). The next step would then be a packet capture or ETW trace (`pktmon`), which needs admin rights or IT approval and the researcher's decision. |
| **Optional second 120 s segment** | Gateway and MediaMTX with no reader, to test whether a reader changes the hold rate. |

**Separately, for decision (not started):**
- the trial-start gate defect (O1.4) and the missing video-continuity record for observation intervals;
- O2 (for example, an opt-in wait for the camera to reappear before the first unicast reconnect).

### 13.31 Approved M1 TCP-counter diagnostic run: every hold release coincides with a TCP retransmission (13 Nov 2026, 15:50–15:54)

**Approval and constraints:**
- The researcher approved a read-only TCP-counter sampler and Camera A ping logging during shutdown.
- Camera A only (Camera B unplugged, confirmed by the researcher). Existing 120 s gateway limit.
- Unchanged: runner, gateway, encoder, keyint 20, 150 ms age guard, resync policy and the M1 player.
- The optional no-reader segment is deferred until this result has been reviewed.

**Run:**
- `tools/run_m1_tcp_diagnostic.ps1`, which wraps the unchanged `run_stage2.ps1 -NetworkScope EthernetScoped` (M1 default, 60 s preview). The plan-only output matched the validated default.
- **Folders:**
  - diagnostics: `results/m1_tcp_diag_20261113_155016/`;
  - runner: `results/stage2_runner_20261113_155021/`;
  - gateway: `results/gw_20261113_155057_A_stage2/`;
  - pre-run checks: `results/m1_tcp_diag_prep_20261113/`.
- **Backup:** `backups/20261113_m1_tcp_diagnostic_evidence/` (32 files, SHA-256 manifest).
- **Outcome:**
  - runner `completed`, no deviations;
  - Stage 2 integrity S1–S11 all PASS;
  - calibration unchanged; device gaps 0;
  - Wi-Fi 18/18;
  - clean final check (no processes, port 8554 free);
  - 7 receiver freezes and 10 rejected late pairs in about 58 s of reception;
  - gateway stale resyncs: left 1, right 8 (one each at start-up).

**What the counters are** (`tools/tcp_counter_sampler.py`):
- **Source:** `iphlpapi.GetTcpStatisticsEx` (IPv4 and IPv6).
- **Scope:** **system-wide totals per address family**, covering all TCP connections on all interfaces. They are **not per connection**. Per-connection statistics (`GetPerTcpConnectionEStats`) would need collection switched on, which needs admin rights; not attempted.
- **Loopback included** (`tools/tcp_counter_loopback_check.py`, `m1_tcp_diag_prep_20261113/loopback_check.json`):
  - 20,000 private 127.0.0.1 round trips added 80,016 OutSegs, against 10 in an equal idle window;
  - **Retransmission positive control:** SYNs to a full 127.0.0.1 backlog were silently dropped and retried, and RetransSegs rose by 21. So loopback retransmissions are counted, and a lack of steps would be informative.
- **Sampling:** requested 10 ms; actual median 10.00 ms, p99 10.6 ms, max 15.7 ms (21,400 samples in 214 s).
  - Call cost: median 55 µs.
  - Sampler CPU: 0.99 % of one core.
  - Clock: `time.monotonic_ns` (QueryPerformanceCounter), the same clock as the gateway and Unity.
- **Background:**
  - idle baseline (60 s, nothing streaming): 12 IPv4 retransmission steps (0.2/s);
  - in-run, outside the hold neighbourhoods (66 s of streaming): 14 steps of 1 segment (0.21/s).
- **The minimum timeout the stack reports** (`dwRtoMin`) is 5. The hold length suggests an effective timeout of about 300 ms; that inference is unverified.

**Result (O1)** (`tools/analyse_tcp_holds.py`, `tcp_holds_analysis.json`):

| Measure | Result |
|---|---|
| Holds (mid-stream stale resyncs, Unity reader connected) | 7, **all on the right eye**; hold 304–314 ms (median 306 ms) |
| Holds with an IPv4 RetransSegs step within ±20 ms of the release | **7 of 7**. Each step was **exactly 1 segment**, in the 10 ms sample containing the release (the sample ended 0.7–5.6 ms after the first held data reached Unity). |
| Holds with a step near the onset | 0 of 7 |
| Chance of a background step in one ±20 ms window | 1.05 %. Expected chance matches: 0.07 of 7. |

**Interpretation:**
- **Strongly supported:** each hold ends with a single TCP segment retransmission somewhere on the host, at the moment the held data is released. Together with §13.30 (hold upstream of MediaMTX's fan-out, backing up into the gateway's write), the best explanation is a lost segment on the gateway → MediaMTX loopback connection, recovered by retransmission after about 300 ms.
- **Not proven:** that the retransmitted segment belonged to the camera connection. The counter is aggregate.
- **Not known:** why a loopback segment is lost (stack or filter-driver drop; receive-side resources).
- **Decisive tests:** a packet capture or ETW trace (`pktmon`), which needs admin rights or IT approval and the researcher's decision.

**O2 (kept separate; `tools/analyse_o2_shutdown.py`, `o2_shutdown_timeline.json`; times after the gateway saw its stop file):**
- **0.1 s:** Camera A stops answering ping. The first unicast reconnect starts at about 0.25 s.
- **8.1 s:** **ICMP replies resume**, but depthai first reaches the camera's bootloader only at **49.5 s**.
- **49.7–50.4 s:** a burst of **871** retransmitted segments (system-wide). Ping is lost from 52 s.
- **57.2 s:** "Device crashed, but no crash dump could be extracted".
- **65.3 s:** the second attempt reaches the bootloader. A burst of **936** retransmitted segments follows, then the calibration read succeeds (72.6 s wait in total; calibration unchanged).
- **Ping flapping:** 41 of 80 replies, with outages at 36–43, 52–57, 58–65 and from 68 s.
- **Reading:**
  - ICMP returned about 41 s before depthai could connect, so **ping availability does not indicate application readiness**;
  - the "crash" follows a connection that dropped during the first firmware hand-over;
  - large retransmission bursts accompany **both** hand-overs, the failed one and the successful one, so they do not distinguish them.
- **Status:** unresolved.
- **Possible reconnect change (proposal only; not implemented):** in scoped mode, wait before the first unicast attempt, and/or bound each attempt, evaluated in a separate run. Broadcast discovery will **not** be reintroduced on the university network.

### 13.32 Video readiness and continuity fixes (Unity; 13 Nov 2026; offline-verified; NOT committed)

Made after the §13.31 evidence was preserved, as the researcher instructed.
- **Unchanged:** the gateway, encoder, keyframe interval, the 150 ms freshness limit, the resync policy and the M1 player binary.
- **Changed:** Unity only. The working tree is uncommitted on top of `807ef39`.

**1. Readiness (fixes the §13.30 O1.4 defect)**

New pure C# file `Experiment/Core/VideoStatus.cs`:
- `IFeedSource`, `FeedTracker`, `VideoStatus`, `IVideoStatusSource`, `VideoReadiness` and `ViewContinuity`.
- **Genuine pairs only:** a feed accepts a pair only when the receiver has copied a genuinely received pair (`PairsCopied > 0` with a presenter row). The tracker's counter starts at 0. The empty, zero-filled start-up buffer is never uploaded or counted.
- **What `video_ready` (TrialReset) requires,** from both new receivers:
  - **validated:** eye and camera identity passed; freshness label `fresh` (absolute, trusted clock) or `fresh_relative` (offline replay);
  - **current:** on-screen age within the receiver's own `fresh_age_ms`, 150 ms.
- **Visibility:** not required at reset, because the plate is behind the reset screen. The observation gate checks it later.
- **Reset:** readiness resets with every receiver restart (new feeds per generation, recorded in `video_prepared`) and every source change.
- **New `video_ready` session event:** records when readiness was reached, with each camera's sequence number, freshness and ages.
- **Loading state:** the plate shows the existing neutral "Waiting for video" veil until a pair arrives.
- **Unchanged:** `CameraFeed` keeps its public API.
- **Receiver change:** `StereoReceiverBehaviour` gains only a read-only `StopReason` property.

**2. Truthful status of the image on screen**
- **Ages tracked separately:**
  - **age at presentation:** absolute where the clock is trusted (live Camera A); relative (excess delay) for replay;
  - **age on screen:** age at presentation plus the time the image has stayed on screen.
- **New `Stale` condition:** applies when the on-screen age exceeds 150 ms (or the pair is not validated).
  - Caption "Image not current" in amber, instead of "Live"; camera-wing status "Image not current"; amber plate frame.
  - The image is dimmed: the dim fades in over 100 ms, so a single-frame excursion is not a flash, and it clears at once when a current image arrives.
  - The state flips at exactly 150 ms; only the visual dim is eased.
- **Unchanged after 500 ms:** "Video interrupted · x.x s" still appears, now over a dimmed image.
- **Source exhaustion vs failure:** a recording that played to its end (`replay_done_and_drained`, file replay only) is `ended`. A live stream that closes, or a backend error, is `failed`. Both keep the existing "Video unavailable" veil, and the reason is recorded.
- **Recorded:**
  - `view_frames.csv` gains `shown_age_at_presentation_ms`, `shown_on_screen_age_ms`, `shown_age_basis` and `plate_visible`;
  - `video_state` UI events carry the full status;
  - the client `video_state` vocabulary becomes `live` (current only), `not_current`, `interrupted`, `waiting` and `unavailable`. `verify_s3_run.py` was updated to accept it.
- **Sized on live data:** in the §13.28 walkthrough, outside freezes, 3 images in 93 s of Camera A briefly exceeded 150 ms on screen, for about one render frame each (`walkthrough_diagnostics_20261113/onscreen_age_check.txt`).

**3. Continuity records and the observation gate** (`TrialRuntime`)
- **Gate:** the prescribed observation interval starts only on a **valid visible view**: the selected camera is current and the plate is showing it.
  - If the view is not valid, the start is deferred and recorded (`observation_deferred` with the video status; flag `observation_start_deferred_for_video`).
  - `observation_begin` records `start_deferred_ms` and the video status.
  - The interval itself keeps its full length.
- **During the interval:** continuity is sampled every tick (`ViewContinuity`). `observation_end` carries:
  - valid and not-valid milliseconds;
  - each interruption (offset, duration, state, reason, last and resumed sequence numbers, maximum on-screen age).
- **On a loss:** the episode is flagged `observation_video_interrupted`. The interval is **not restarted, extended or excluded**.
- **Video status is also recorded at:**
  - the SAGAT freeze (plus whether the observation was interrupted);
  - view restoration (and timeout);
  - the first commitment (plus continuity from decision-ready to first commitment; flag `decision_video_interrupted`).
- **CDP summaries:** every summary gains a `video` block.
- **No scoring rule:** validity values are unchanged.
- **View restoration** now requires a valid visible view of the primary camera for **every** source, where before it applied to live Camera A only.
- **Offline-only exception:** recorded footage that has genuinely ended is accepted under the existing `development_override` policy, as before, with the flag `observation_on_exhausted_recording_development_override`. It never applies to a live source.

**Verification (offline; evidence `unity/Phase2Client/test_results/video_readiness_20261113/`):**

| Check | Result |
|---|---|
| Defect reproduction (red check) | With the old acceptance logic temporarily restored in the tracker, `EmptyStartupBuffer_IsNotAFrame_FeedNotReady` **failed** ("an empty start-up buffer must never be accepted as a frame"); the other 6 passed. The fix was restored. |
| New tests | `VideoReadinessTests` 7, `VideoGateTests` 3, model test 1: all pass |
| EditMode (all) | **194/194** (183 before + 11 new) |
| PlayMode | 5/5 |
| S4 player, scripted demonstration | all 24 player checks; `verify_s4_session.py` 23/23 |
| S4 accelerated full session | 26/26 (simulated display: always valid, unchanged) |
| S3 / S3.1 scripted players | 63/63 and 39/39; `verify_s3_run.py` PASS (pixel checks and participant-text lint) |
| S2 player | `verify_s2_run.py` OVERALL PASS |
| Players rebuilt | S4, S3, S2. M1 **not** rebuilt; its only source change is a read-only property. Scene files were regenerated by the builds and restored (IDs only). |

**Effects on offline replay and synthetic Camera B** (from the S4 scripted run):
- **Readiness now comes 1.0–1.5 s after each receiver restart,** when replay sources finish the receiver's 20-pair relative-freshness warm-up (`unverified` until then). The old placeholder passed at about 58 ms.
- **Recorded stalls are now reported truthfully.** The recorded Camera A footage contains real stalls from its capture run, and they now show as stale or interrupted.
  - One formal observation start was deferred by 405 ms: no new image for 451 ms when the CDP opened.
  - One observation was flagged with 649 ms not valid.
- **Synthetic Camera B:** stayed current throughout.
- **Exhausted footage:** handled as above (`ended`, development override only).

**Not verified:** a live run with the fixed S4 player. That needs a separate approval. The live smoke runner (`-Player S4Smoke`) or the demo runner (`-Player S4Demo -ExtendedTest`) would exercise it.

**Recovery-policy decisions for the researchers (not settled; nothing invented):**
- **R1. Deferred start:** how long the observation start may be deferred for video, and what follows. Options include a facilitator `video_loss` interruption, then terminate and replace. At present it waits indefinitely and the facilitator can act.
- **R2. Loss inside the interval:** keep and flag (current), restart after recovery, extend by the lost time, or invalidate and replace the episode. Is there a minimum loss that counts?
- **R3. SAGAT after an interrupted observation:** probe anyway (current) or not.
- **R4. Losses between decision-ready and first commitment:** flag only (current), or more.
- **R5. Development override for exhausted recordings:** keep for offline development only, or remove.
- **R6. What the participant is shown during a deferral:** currently the "Observe" status over the loading or dimmed plate.

**O2 reconnect proposal (separate; not implemented; based on §13.31):**
- **Evidence:**
  - the scoped first unicast attempt begins about 0.25 s after the stop, while the camera is rebooting, and only reaches the bootloader at about 49.5 s;
  - ICMP is back at 8.1 s, but that does not show the application is ready;
  - the isolated path, which waits for discovery to see the bootloader, reconnects in 8–13 s.
- **Proposal:** an opt-in scoped variant that:
  - waits for ICMP replies to resume, plus a fixed settle time;
  - then makes bounded unicast attempts (depthai search and connect timeouts);
  - all **without broadcast discovery**.
- **Evaluation:** one bounded run comparing `waited_s`, attempts and the "Device crashed" line. Approval needed.

### 13.33 Live verification of the video readiness and continuity fixes (13 Nov 2026, 17:13–17:21; fixes still NOT committed)

**Configuration:**
- **Run settings:** existing bounded extended run (`-Player S4Demo -ExtendedTest -GatewaySeconds 600 -PreviewSeconds 525`), Camera A only (confirmed by the researcher), synthetic Camera B, simulated robot, the researcher as participant.
- **Unchanged:** encoder, keyframe interval, 150 ms limit, network guards and resync policy. No faults injected; O2 not implemented.
- **Change since §13.32:** during an observation-start deferral the participant status reads the neutral "Waiting for video" (hold `awaiting_video`); the observation hold and its wording start only with the interval.
  - `observation_begin` now logs `exhausted_recording_development_override` and labels the behaviour provisional.
  - Re-verified offline: EditMode 194/194; S4 script all checks and 23/23.
- **All of the following are provisional development behaviours, not approved research validity or scoring rules:** the deferral, the continuity logging, the flagging without restart or extension, and the exhausted-recording exception.

**Run:**
- **Folders:** runner `camera_gateway/results/stage2_runner_20261113_171347/`.
- **Outcome:**
  - runner completed, no deviations;
  - player exit 0 after 301 s (`application_quit` on the completion screen);
  - Wi-Fi 64/64; clean final check; calibration unchanged;
  - fresh displayed pairs 5008/5008; capture-to-selection median 87.7 ms;
  - gateway stale resyncs 2 left / 16 right: the loopback holds continue, since the transport was not changed;
  - post-run reconnect 76 s (O2 recurs as before).
- **Verification:** `tools/verify_live_video_fixes.py` wrote `live_video_verification.json`.

| Check | Live result |
|---|---|
| **V1** No empty buffer accepted | **PASS.** After each of the 3 receiver restarts, both cameras reported `waiting` until a pair arrived; the status that left `waiting` named a pair that receiver displayed. No render frame showed a state without a received pair. `video_ready` came 1.0–1.6 s after each restart, with received current pairs (A `fresh`, absolute; B `fresh_relative`). No Site Window frame without an image was visible at a trial start (0, against 514 ms in §13.28). |
| **V2** Observation starts only on a current, visible view | **PASS with one logged exception.** 5 of 6 intervals began on a current, visible view, rendered within 5 ms. The exception: B1-T1 CDP-middle began on synthetic Camera B **after its recording had ended**, under the explicit development override, logged and flagged. It applied to the recorded source only, never to live Camera A. **No deferral occurred live**, so the deferral path and its "Waiting for video" status are **untested live** (offline tests only). |
| **V3** Image on screen beyond 150 ms loses "Live"; interruption message | **PASS.** Of 12,782 visible render frames, **0** were labelled live with on-screen age over 150 ms. "Interrupted" appeared only after more than 500 ms without a new image (15 transitions, 0 early). Dimming follows the logged plate condition; pixels were not measured live. |
| **V4** Continuity at observation, SAGAT freeze, restoration and first commitment, with source and frame references | **PASS.** Every record carries camera, source, mode, receiver generation and a sequence number that the named receiver displayed. Losses were recorded live (see below). |
| **V5** SAGAT hides all imagery, then restores a current view before decisions | **PASS.** 3 probes: the plate was off within 1 ms of each freeze, with 0 visible frames during the 2.5–5.2 s probes. Each restored a current, visible view of the primary camera, and decision-ready followed the restoration. |
| **V6** Categories distinguishable | **PASS, with a discrepancy** (exhaustion drain, below). Startup waits 6; camera switches 13; source exhaustion 3 (`ended`, `source_exhausted`); unexpected not-current or interrupted states of the visible camera 21. **Receiver failure: untested live** (none occurred). |

**"Image not current" frequency** (visible render frames; the threshold was not changed):
- **Camera A** (143 s visible): 15 episodes, 5.4 s in total (6.3 per minute).
  - **8 brief excursions** under 100 ms (17–65 ms, median 33 ms: one to four render frames), during otherwise normal 20 fps delivery. That is about 3.4 per minute. With the 100 ms fade, these reach at most about 40 % of full dimming, and the caption flips for that long.
  - **7 longer episodes** of 332–999 ms, matching the loopback holds; 5 of them reached "Video interrupted".
- **Camera B** (70 s visible): 2 episodes, 2.4 s and 2.9 s. Both are the exhaustion drain.

**Losses recorded at formal measures:**
- **Observations:**
  - B1-T1 CDP-early: a **33 ms** Camera A excursion, flagged `observation_video_interrupted`;
  - training CDP-P3: Camera B's recording ran out during the interval (2.7 s not valid), flagged;
  - B1-T1 CDP-middle: Camera B ended before the interval (the exception above).
- **First commitments:** 2 were made with Camera B `ended` and 1 during its drain (`interrupted`). Decision-period interruptions were recorded (up to 4 per episode).

**Discrepancies and findings (not fixed in this task):**
1. **Exhaustion drain is shown as an interruption.**
   - After a recording's last frame, the receiver waits a fixed 3 s drain before declaring `replay_done_and_drained`.
   - For those 3 s, the plate shows "Image not current", then "Video interrupted", before "Video unavailable". The records separate it afterwards (the verifier labels it `exhaustion_drain_shown_as_not_current`, 6 transitions), but the live status cannot.
   - **Possible fix, for decision:** expose the receiver's "source finished, draining" state so the feed reports `ended` immediately.
2. **Brief excursions flag observations.** A 33 ms excursion flagged an observation. Whether a minimum duration counts is decision **R2**; nothing was changed.
3. **S6 / session integrity FAIL from an existing S4.1 counting issue, unrelated to the video fixes.**
   - The session completed (status `completed`, Closed), but the runner's `inactive_locations` check found 3 against 2 expected.
   - In B2-T1, the inactive location "early" was recorded as an autonomous release **and then** as the location of the participant's later unscheduled hold. The check adds both counts.
   - §13.28 passed because its unscheduled hold reached the inactive location before any autonomous record.
   - Needs a separate decision on the counting rule.
4. **Not exercised live:** the deferral (and its "Waiting for video" status), receiver failure, and the startup "Waiting for video" veil. The plate is behind the reset screen until video is ready, so the waiting state was recorded but not shown.
5. **UI event timestamps** (`ui_events.jsonl`) are stamped on the session clock before that frame's advance, about one frame behind the receiver's display stamps. The verifier therefore checks readiness by frame reference. This is a logging property, not a behaviour change.
6. **The loopback holds (O1 transport) continue unchanged:** 9 unexpected visible interruptions, longest 1.06 s. The fixes make them truthfully visible; they do not remove them.

**Status:**
- The fixes and the new verifier stay **uncommitted** for review.
- **R1–R6** stay open for reconciliation with the methodology. R2 is now informed by the 33 ms case.
- The **O2** proposal is preserved for a separate decision.

### 13.34 Focused corrections after the live verification (13 Nov 2026, evening; offline-verified; NOT committed)

**Scope:** inactive-location counting, recorded-source exhaustion, rendered-pixel proof of the stale dim, and a reconciliation of stale episodes with interruptions.
- No other S4.1 rule was changed.
- Unchanged: transport (O1), O2, encoder, keyframe interval, the 150 ms threshold and the resync policy.
- No live run was made: none was needed for these corrections.

**1. Inactive-location counting (integrity correction)**
- **Rule:** `TrialRuntime.DistinctInactiveLocations()` counts each predefined inactive location once per trial instance. A replacement trial has its own uid, so it counts separately.
- **Both records are kept and linked:**
  - the autonomous `inactive_location` record carries `inactive_location_id` and `first_reached_by` (`autonomous_release` or `unscheduled_hold`, plus `linked_unscheduled_episode`);
  - an `unscheduled_episode_open` at an inactive location carries the same `inactive_location_id`, `inactive_location_first_reached_by`, `inactive_location_ref_gt` and `counts_as_additional_inactive_location: false`.
- **`trial_end`** reports:
  - `inactive_locations` (distinct);
  - `inactive_location_ids`;
  - `inactive_autonomous_records`;
  - `inactive_reached_by_unscheduled_episode`.
- **Regression tests (`InactiveLocationTests`):**
  - the B2-T1 order: autonomous release, then a hold in the gap. Count 1; the earlier formula gave 2. Both records are linked.
  - the hold-first order: the location is reached initially by the hold. Count 1.
- **Reanalysis of the §13.33 run** (`tools/reanalyse_inactive_locations.py`; output `results/stage2_runner_20261113_171347_reanalysis/`; raw `session_events.jsonl` hash unchanged):

  | Rule | Inactive-location total | Expected |
  |---|---|---|
  | Old | 3 | 2 |
  | New | **2** | 2 |

  - B2-T1 "early": autonomous record (seq 351), then the linked hold (seq 356).
  - No other integrity check failed.
  - S6 had failed **only** on `session_integrity_pass`.
  - **The integrity failure is fully explained and corrected.** The recorded run itself is not rewritten.

**2. Recorded-source exhaustion**
- **New read-only signals:**
  - `StereoPresenter.PendingCompletePairs`;
  - `StereoReceiverBehaviour.SourceEndOfFile` (file replay only: the backend has finished reading);
  - `StereoReceiverBehaviour.FinalFramesPresented` (EOF confirmed and no complete pair left to present).
  - The receiver's own drain and stop reasons are unchanged.
- **Feed behaviour:** a finite recording reports `ended` / `source_exhausted` (`eof_confirmed_final_frames_presented`) at that moment. It no longer shows "Image not current" then "Video interrupted" during the receiver's 3 s drain.
  - A pause in a recording **before** EOF is still reported truthfully as not current or interrupted.
- **Failures kept distinct:**
  - `decoder_or_backend_error`;
  - `live_source_lost:<reason>` (live RTSP; for example `stream_ended`);
  - `receiver_ended:<reason>`.
  - A live source can never be "exhausted".
- **Development override:** the explicitly logged development-only exhausted-recording override is unchanged and never applies to live sources.
- **Verified offline:**
  - unit tests;
  - S3 script `exhausted_footage_unavailable_not_looped` now also requires that the plate never passed through "interrupted";
  - S4 script: Camera A went `live` → `unavailable (source_exhausted, eof_confirmed_final_frames_presented)` directly.
- **Live verification:** not yet seen live.

**3. Short freshness losses:** no behaviour change.
- The 150 ms threshold is kept.
- Every measured loss, including the 33 ms event, is retained with duration and context: offset, state, reason, last and resumed sequence numbers, maximum on-screen age.
- `observation_end` now states that the flag is not an exclusion or scoring rule (R2 open).
- No minimum-duration threshold, restart or scoring change.

**4. Verification** (evidence `unity/Phase2Client/test_results/corrections_20261113/`)

| Check | Result |
|---|---|
| EditMode | **198/198** (4 new: 2 inactive-location, 2 exhaustion/failure reasons) |
| PlayMode | 5/5. The new pixel step first stalled in batch editor runs, because `WaitForEndOfFrame` never fires in batch mode; fixed by waiting one frame there, where no capture is made anyway. |
| **Stale dim changes the rendered image** (S3 player, 1920 × 1080; Camera B display frozen by the scripted developer tool, so the plate texture is constant) | Undimmed reference (Live, dim 0) against dimmed (**Stale**, dim 0.6) over **953,260 plate pixels**: linear-light fit `dimmed = 0.4006 · undimmed + 0.63` (expected slope 0.400); max residual 0.68, mean 0.15 (0–255 linear); mean brightness 127.7 → 85.2 sRGB. Same result in the Interrupted state. Dim back to 0 when current (`stale_dim_cleared_when_current`). |
| S3 / S3.1 scripted players | 66/66 (3 new checks), 39/39; `verify_s3_run.py` PASS |
| S4 script / accelerated / S2 | 23/23 (all player checks) / 26/26 / PASS |
| Players rebuilt | S3, S4, S2 (M1 not; its receiver gained only read-only properties). Scenes restored. |

**Reconciliation of "7 longer stale episodes" with "9 visible interruptions" (§13.33 run)**
(`results/stage2_runner_20261113_171347_reanalysis/stale_vs_interruptions_reconciliation.txt`)
- **"Visible interruption"** (walkthrough summariser): Camera A on screen and **no new image for ≥ 125 ms** (the receiver's freeze threshold), measured between images.
- **"Image not current" episode** (live verifier): render frames whose **on-screen age** (age at presentation + time shown) **exceeds 150 ms**. It starts about 62 ms after the last new image (150 − ~88 ms presentation age) and ends at the next image.
- **The 9 interruptions:**
  - **7 long gaps** of 399–1065 ms are the 7 longer stale episodes (332–999 ms, each about 66 ms shorter than its gap);
  - **1 short gap** of 133 ms produced a 65 ms stale episode;
  - **1 render hitch** of 145 ms on the first Site Window frame: the window was not redrawn, so no frame could be labelled.
- **The other 7 brief stale episodes** (17–34 ms, 1–2 frames, peak age 164–177 ms) had no image gap ≥ 125 ms: freshness excursions without a receiver freeze, which the summariser does not count.

**Remaining limitations:**
- **Untested live:** observation-start deferral (and its "Waiting for video" status), receiver failure, and the corrected exhaustion transition.
- **Loopback holds (O1 transport):** continue unchanged.
- **Open:** R1–R6 (R2 informed by the 33 ms case); O2 proposal; broader UI polish.
- **Uncommitted** for review: the Unity changes, the gateway tools (`verify_live_video_fixes.py`, `reanalyse_inactive_locations.py`, the TCP diagnostic tools) and `verify_s3_run.py`.

### 13.35 Development baseline accepted and committed (13 Nov 2026, evening)

**Accepted** by the researcher as the development baseline, with the documented live-verification gaps retained:
- readiness;
- stale-display handling;
- continuity logging;
- inactive-location counting;
- recorded-source exhaustion.

**Commit:**
- Unity `d7371d6` (`d7371d608eb14b0a1d2c29c9bb20e242abc9cab3`) on local `master`; nothing pushed.
- Contents: source, tests, `Tools/verify_s3_run.py` and the Unity README.
- The working tree is clean afterwards.

**Backup:** `backups/20261113_video_baseline_checkpoint/` (SHA-256 manifest). It holds:
- the gateway diagnostic and verification tools;
- the external documentation;
- the reanalysis and live-verification outputs.

Original run records and earlier backups are unchanged.

**Limitations kept explicit:**
- **Untested live:** observation-start deferral, receiver failure, and the corrected recording-exhaustion transition.
- **Provisional:** R1–R6.
- **Unresolved:** streaming continuity (the ≈ 310 ms loopback holds, O1), the O2 shutdown/reconnect anomaly, and the O3 dual-camera addressing anomaly.
- **No final research exclusion or scoring policy** has been established by these fixes.

### 13.36 Proposal: connection-specific capture of the ≈ 310 ms gateway → MediaMTX holds (13 Nov 2026; PREPARED, NOT RUN; needs approval and elevation)

**Inspection** (read-only; nothing installed, enabled or started):

| Item | Finding |
|---|---|
| Account | Not elevated (Medium integrity). Not in Administrators (S-1-5-32-544) or Performance Log Users (S-1-5-32-559). |
| `pktmon` | Present; its driver refuses this account ("Access is denied"). Whether it sees loopback traffic at all is unconfirmed: its packet path is NDIS-based, and loopback does not pass through NDIS. |
| ETW (`logman`, `wpr`, `tracerpt`) | Present. Creating a kernel-provider session needs Administrator (or Performance Log Users). |
| Microsoft-Windows-TCPIP provider | Keywords include `TcpipTcb`, `Transfer`, `Loopback`, `SendPath`, `ReceivePath`, `Dropped` and `Packet`. It cannot be filtered by port at source. |
| Microsoft-Windows-Winsock-AFD provider | Socket-level send and receive events per process (`AFD_KW_STREAM`, `SOURCE_WINSOCK`, `SOURCE_TRANSPORT`). |
| Npcap / Wireshark / tshark | **Not installed.** A loopback packet capture filtered at source (`host 127.0.0.1 and tcp port 8554`) would need Npcap installed (admin, IT approval); not proposed first. |

**Proposed capture** (`camera_gateway/tools/capture_o1_loopback_etw.ps1`; plan-only by default; refuses unless elevated, isolated and `-Armed`):
- **Built-in ETW only:** TCPIP (TCB, transfer, loopback, send and receive paths, drops; verbose) and Winsock-AFD (stream socket send/receive).
- **Clock:** QPC (`-ct perf`), the same clock as the gateway (`time.monotonic_ns`) and Unity. Events can be aligned with `sent.csv`, `captured.csv` and `arrivals.csv` without conversion.
- **No unrelated traffic** *(corrected in §13.37: Wi-Fi off reduces external traffic, but the system-wide kernel providers still collect unrelated local metadata before filtering)*: runs only in the validated **Isolated** network mode, with Wi-Fi turned off by the researcher. No university or Wi-Fi traffic can exist during the capture. After decoding, events are filtered to the 127.0.0.1:8554 connections (two publisher, two reader); the raw `.etl` and XML are deleted unless `-KeepRaw` is chosen. *(Superseded in §13.37: raw files are now retained by default until validated extraction.)* No payload is recorded (TCP metadata only).
- **Bounded:** the default M1 preview (`run_stage2.ps1 -NetworkScope Isolated`) within the unchanged 120 s gateway limit; capture hard cap 400 s; circular file cap 512 MB. Transport settings, keyframe interval, 150 ms limit and resync unchanged.
- **Step 1 — feasibility (-Feasibility, ~10 s, no camera, same elevated and isolated window):** local loopback traffic plus the forced local SYN retransmission from `tcp_counter_loopback_check.py`. It shows which TCPIP/AFD events appear for loopback data, ACK/window, retransmission and drops, and the data volume.
- **Then:** the event parser `tools/analyse_o1_etw.py` is written against the observed schema, and only then is the camera run made.

**What would distinguish the explanations** (gateway → MediaMTX connection, around each hold found from `sent.csv`/`arrivals.csv`):

| Hypothesis | Expected signature |
|---|---|
| **Retransmission recovery** (lost segment) | A data segment sent at the hold onset; no ACK covering it; a **retransmission of that sequence about 300 ms later** (retransmit-timeout event), immediately followed by an ACK and the burst release. Ideally a `Dropped` event at the onset with its drop reason. Gateway AFD send calls complete normally until the send window fills, then one blocks until the ACK. |
| **Receiver backpressure** (MediaMTX not draining its socket) | MediaMTX's ACKs advertise a **shrinking receive window down to zero**; zero-window probes from the gateway; a window update when MediaMTX reads. **No retransmission of data, no drop.** MediaMTX-side AFD receive completions absent during the hold. |
| **Server-side reading delay without window exhaustion** | TCP ACKs keep arriving promptly (the kernel acknowledges regardless of the application). No retransmission, window not exhausted. MediaMTX's AFD **receive completions delayed by about 300 ms** while data sits in its socket buffer. The gateway write would block only if the windows filled. |

**What the capture cannot establish:**
- **Why a loopback segment was lost,** unless a `Dropped` event gives a reason. Even then, attributing a drop to a specific filter driver (for example security software or WFP callouts) needs WFP state (`netsh wfp`, admin) and probably IT involvement.
- **MediaMTX's internal scheduling** beyond its socket calls (AFD shows when it read, not why it did not).
- **Behaviour on the inter-site (Roseworthy–North Terrace) network,** on non-loopback deployments, or on other machines.
- **Anything about the camera link.**
- **Causation for any single freeze,** beyond timing coincidence.
- **Whether the TCP kernel events are complete** (ETW can lose events under load; lost-event counts will be reported).

**Exact requirement to run:** an **elevated Administrator PowerShell** on this laptop for about 10 minutes (feasibility about 1 min, then the camera run about 4 min), started by the researcher with IT-granted temporary elevation or by IT staff. No software installation. No system setting changed; Wi-Fi is turned off by the user, as in the earlier isolated stages. Claude Code is offline during the isolated window, so analysis follows afterwards.

**Optional alternative (needs software install and IT approval):** Npcap with loopback support plus `dumpcap`, filtered at source to `tcp port 8554 and host 127.0.0.1`, headers only (snaplen ≈ 96).

**Not started:** no capture or live test was launched.

### 13.37 O1 capture preparation revised; parked pending IT (13 Nov 2026, late)

**Parked.** No capture run. No permission bypass, software install or security or setting change. Application and transport settings unchanged.

**Corrections to §13.36:**
- **Unrelated metadata:**
  - Turning Wi-Fi off *reduces external* traffic.
  - It does not prevent unrelated local metadata being collected. Microsoft-Windows-TCPIP and Microsoft-Windows-Winsock-AFD are **system-wide kernel providers**, and `logman` offers **no port, address or process filter at collection**. The raw trace therefore contains events of other local connections and processes until post-processing.
- **Unverified fields:** no packet-level ACK, receive-window or socket-read evidence is promised until the feasibility step verifies those fields.

**Filters, made explicit** (`camera_gateway/O1_ETW_CAPTURE_INSTRUCTIONS.md`):

| Stage | What filters | Detail |
|---|---|---|
| Collection | Provider, keyword mask, level; time and size bounds; QPC clock | TCPIP `0x0000010300400104` (TcpipTcb, Transfer, Loopback, SendPath, ReceivePath, Dropped; `Packet` NOT enabled) at level 5; Winsock-AFD `0x000000000000000E` (STREAM, SOURCE_WINSOCK, SOURCE_TRANSPORT) at level 5; ≤ 400 s; ≤ 512 MB circular |
| Post-processing | Decoded copy only | TCP 4-tuples involving 127.0.0.1:8554; AFD events of the gateway, MediaMTX and Unity process ids. Everything else excluded from the outputs. |

**Feasibility step now establishes what the providers expose:**
- **Traffic:** `tools/o1_etw_feasibility_traffic.py` generates known local 127.0.0.1 activity with QPC and UTC markers (tested here without capture; 5.3 s):
  - a timed connect;
  - a 2,000-message transfer;
  - a 1 s receiver stall (the socket accepted 180 kB before blocking);
  - a forced SYN retransmission.
- **Analysis:** `tools/analyse_o1_etw_feasibility.py` (parser self-tested on synthetic tracerpt-format XML) reports, per provider and event, the field names actually present.
- **Capabilities tested:**
  - connection identity and process attribution;
  - sequence and ACK numbers;
  - window information;
  - retransmission events, checked against the forced SYN retries;
  - drop reasons;
  - byte counts;
  - socket or endpoint ids;
  - timestamp alignment against the connect marker;
  - lost events and buffers.
- **Gate:** the camera capture is refused until a feasibility report exists.

**Retention:**
- **Kept by default:** the raw `.etl` and decoded XML are **retained** in `results/o1_etw_*/raw/` (local disk only; SHA-256 in `raw_sha256.txt`) until extraction and validation succeed and the researcher decides.
- **Deletion:** `-DeleteRawAfterValidation` deletes them only after a passing validation. Nothing deletes the only usable evidence automatically.
- **To agree:** the retention arrangement itself, with the researcher (and IT if required).

**Rights:**
- The wrapper accepts either temporary **Performance Log Users** membership (S-1-5-32-559; least privilege; Microsoft documents that this group may control ETW sessions) or an elevated Administrator session.
- Tested on this account: plan-only works; armed refuses (exit 3); no folder or session created.

**IT request (draft, not sent):** `docs/coordination/IT_request_temporary_elevation_O1_capture.md`. It states:
- the minimum rights (Performance Log Users preferred; Administrator fallback, or IT staff at the device);
- about 30 minutes in one window;
- built-in `logman`/`tracerpt` only;
- the scope and data;
- local storage, deletion and cleanup.

**Backup:** `backups/20261113_o1_capture_preparation/` (SHA-256 manifest).

**Restart point:**
- **Researcher:**
  - review and send the IT request;
  - agree the retention arrangement.
- **When rights are granted, in one window:**
  - Camera A only; Wi-Fi off;
  - run the feasibility step first;
  - review `feasibility_report.json`;
  - only then decide on the camera capture.
- **Afterwards:** write `analyse_o1_etw.py` against the verified schema.
- **Still open:** R1–R6, O2 and O3.

### 13.38 O1 feasibility capture: elevation route and launch preparation (13 Nov 2026, late)

**Elevation:**
- The researcher holds **university-approved local administrator credentials**. The IT request (§13.37) is therefore not needed for elevation and stays an unsent record.
- Elevation goes through the **normal Windows UAC prompt** in a **separate elevated PowerShell** (`Start-Process -Verb RunAs`). The researcher types the credentials into Windows directly; Claude and the scripts never request, read, store or log them. Claude keeps running unelevated.

**Authorised:** only the **10 s no-camera feasibility capture**. Its events and fields are to be reviewed with the researcher before any camera capture.

**Wrapper additions:**
- `-Out` (explicit folder);
- `-WaitForIsolationMinutes` (the window opens online and waits up to N minutes for Wi-Fi off; isolation must then hold for 10 s; nothing starts on timeout);
- `-PauseAtEnd`;
- a console transcript;
- a trap that stops the session on any error and keeps the files;
- a session-stopped check.

**Retention:** raw traces are kept locally in the diagnostic output folder until the extracted results are validated and the researcher decides on deletion. They are not uploaded or shared.

**Backup:** `backups/20261113_o1_feasibility_launch/`.

### 13.39 O1 ETW feasibility capture: RUN (no camera); providers expose most of what is needed, with limits (13 Nov 2026, 18:39)

**Run:**
- Authorised 10 s no-camera feasibility only.
- Elevation through the normal UAC prompt in a separate PowerShell; the researcher entered the credentials. Wi-Fi was off during tracing.
- **Folder:** `camera_gateway/results/o1_etw_feasibility_20261113_183840/`.
- **Attempt 1** (`…_182742`): captured nothing and started no tracing. Its console froze in QuickEdit "Select" mode while waiting.
  - Fixes: QuickEdit off for that console; the validated runner's isolation rule; a heartbeat.
  - Backups: `backups/20261113_o1_feasibility_launch/` and `…_launch_r2/`.
- **Tracing:** 5.3 s; 136,540 events; **0 events lost**, 0 buffers lost; session stopped (`session_stopped_check.txt` = 0).
- **Raw files retained locally:** `raw/o1.etl` (31.5 MB) and `raw/o1_events.xml` (207 MB), with SHA-256 in `raw_sha256.txt`. Not uploaded or shared; deletion awaits the researcher's decision.

**Analysis:**
- **First-pass output** (`feasibility_report.json`) gave misleading verdicts, from bare-port matching and the literal time-zone label.
- **Second pass:** `tools/analyse_o1_etw_feasibility_v2.py` → `feasibility_report_v2.json`.
- **Direct checks:** `feasibility_followup.txt`.

| Capability | Result on the KNOWN test connections |
|---|---|
| Connection identity | **Verified.** Events carry `Tcb` plus `LocalAddress`/`RemoteAddress` as `127.0.0.1:<port>` and `Pid` (1031/1033 connect, 1300 rundown, 1038/1043/1044 close). **Caveat:** `Tcb` pointers are **reused** (5 of 174 within 5 s), so the mapping must be bounded by each connection's lifetime. |
| Per-segment send | **Verified.** 1332 `TcpDataTransferSend` (SeqNo, SndUna, SndMax, SndWnd, RcvWnd, Cwnd, RTO, SRtt, bytes): 4,013 events |
| Per-segment receive header | **Verified.** 1601 `TcpRx` (ThSeq, ThAck, ThFlags): 4,013 events |
| Cumulative ACK and send window | **Verified.** 1330 `TcpDataTransferCumAck` (SeqNo, BytesAcked, SndWnd): 2,010 events |
| Delivery to the application | **Verified.** 1157 `TcpDeliveryIndicated` (RcvNxt, NumBytes): 2,000 events |
| Receiver limitation | **Partly verified.** 1626 `TcpLimitingFactor` `ReceiverLimitedBytes` rose above 0 during the receiver stall (max 65,280); send window fell to 16,128. **Zero window was not reached** on the test connection, so `TcpZeroWindowProbingBegin` (1102) appeared only on an unrelated local connection. |
| Retransmission | **SYN retransmission verified** (1186 `TcpConnectRestransmit` and 1351 `RetransmitRound`, with RexmitCount and RTO, on the forced-retry connections). **Data-segment retransmission not verified** on the test connections (none could be provoked); its event types (1187, 1069, 1584) appeared only on an unrelated connection. |
| Drops | **Present with numeric reasons.** 1214 `TcpipTransportPacketDrops`: 52 on test ports, reasons 10, 20 and 30, with socket addresses and packet count. **Reason codes are undocumented**, so they cannot yet be interpreted. |
| Socket calls (Winsock-AFD) | **Verified per process.** 1003 send and 1004 receive, enter→exit durations: send p50 0.01 ms / max 0.32 ms; receive max 0.05 ms; status 0x0. The endpoint maps to a pid (1000 `AfdCreate`). **Endpoint → TCP connection mapping not available** (bind events did not carry the test ports). |
| Timestamps | tracerpt renders correct local-time digits but an **unreliable offset label** (`+10:29` on 136,520 events, `+10:30` on 20; `Get-WinEvent` labels the same digits `+10:30`). **With the label ignored, alignment with the gateway clock is verified:** the P1 connect is +4.1 ms after the marker (marker interval 4.25 ms); the P4 first connect is +1.1 ms after its marker, 1.07 s later. |

**Unrelated metadata in the raw trace:**
- 167 other connections, 9 other processes and 17 other socket endpoints.
- **Including one external connection** (the Wi-Fi address to an internet host on 443), recorded by the connection rundown at session start.
- So even with Wi-Fi off, the raw trace holds metadata of connections that existed before tracing. This confirms the §13.37 correction. The raw files stay local only.

**Does it support the intended connection-specific analysis?** Mostly, with explicit limits.
- **Retransmission recovery:** identifiable on the gateway's (connecting) side, via per-segment sequence numbers, SndUna and SYN-type retransmission events. Data-retransmission events are schema-seen but not verified on a test connection.
- **Receiver backpressure:** observable through RcvWnd/SndWnd and receiver-limited bytes. Zero-window was not verified on a test connection.
- **Server-side reading delay:** observable at process level only (MediaMTX's AFD receive timing). Without endpoint→connection mapping, attribution to one eye's connection must come from timing.
- **Not established:**
  - the meaning of the drop reasons;
  - the accept-side (MediaMTX) Tcb mapping (only one side of the test connection was mapped by address events).

**Camera-capture sizing (a decision before any camera run):**
- **Volume:** the per-segment events (SendPath / ReceivePath keywords) are about 13 per data segment. At an estimated 2,800 segments/s over the four camera connections, a 90 s run would be **about 1 GB of ETL**, more than the 512 MB circular cap (the start would be overwritten), and **several GB of XML** after decoding.
- **Disk:** 814 GB free, so space is not the constraint.
- **Options:**
  - raise the cap, for example to 2 GB;
  - cover only the 60 s M1 preview;
  - decode by streaming, keeping only the 8554 connections.
- **Not decided.**

**Status:**
- **No camera capture.** It is to be reviewed with the researcher.
- **Raw feasibility traces retained locally.**
- Transport and application settings unchanged.

### 13.40 O1 connection-specific camera capture: clean-streaming baseline; INCONCLUSIVE for O1 (13 Nov 2026, 19:19–19:22; approved; not to be repeated automatically)

**Recorded as:** a clean-streaming baseline and an **inconclusive diagnostic for O1**. No hold occurred, so this run says nothing about what causes the ≈ 310 ms holds. **It must not be read as evidence that O1 is resolved.** By the researcher's instruction the capture is not repeated automatically.

**Run** (one 60 s M1 preview, Camera A only; gateway defaults unchanged: 120 s, encoder, keyint 20, 150 ms freshness, resync and network guards):
- Output: `camera_gateway/results/o1_etw_capture_20261113_191856/`. Runner `results/stage2_runner_20261113_191952` (S1–S11 PASS). Gateway `results/gw_20261113_192052_A_stage2`. Unity receiver `unity_rx_20261113_192111_win64player_A_camA_preview`.
- **Ordering as designed up to the player's exit:** pipeline streaming → READY_FOR_TRACE 19:21:03.27 → trace + START marker 19:21:05.95 → TRACE_STARTED 19:21:06.10 → readers connect at 19:21:12.44 (traced from their SYN) → Unity exits 19:22:13.66 → PREVIEW_DONE 19:22:13.66 → 3 s tail → END marker 19:22:16.95 → stop 19:22:19.41.
- **Trace:** 73.5 s; ETL 910,163,968 bytes against the 2 GB sequential cap (cap not reached, start not overwritten); 7,235,440 events, **0 events lost, 0 buffers lost**; no session left after stop (elevated check at stop time).
- **Deviation:** the post-run calibration reconnect (O2) was **partly traced**. The runner does not wait for the trace to stop: it began shutdown 15 ms after PREVIEW_DONE (gateway stop file 19:22:13.72; reconnect waited 8.41 s, connected in 7.81 s, run_end 19:22:30.31). So the first ≈ 5.6 s of the reconnect lie inside the trace. This does not affect the O1 window, because all four streaming connections had closed by 19:22:13.80. If any capture is ever repeated, the runner should wait for a TRACE_STOPPED handshake before shutdown. No change made.
- Gateway: 2 resyncs, start-up only (19:21:02, before the trace began); calibration unchanged; post-run reconnect 8.41 s (isolated mode, consistent with §13.30 O2). Unity: no freeze events; 1,162 fresh pairs; maximum interval 116.6 ms.

**Extraction (validated):**
- `tools/extract_o1_etw.py` streamed the tracerpt CSV: 7,243,052 rows, 0 parse errors, row reconciliation OK.
- 8 relevant instances (4 connections × 2 sides) and both marker connections found.
- Eye identity from `mediamtx.log`:
  - publishers: left 61146, right 61147 (gateway pid 31608);
  - readers: left 61157, right 61158 (Unity pid 20560);
  - MediaMTX pid 30628.
- 24 event types are not in the field schema. Among the kept events these are only Winsock-AFD 1006 / 1007 / 1009 (98 events), stored with positional field names and not used by the analysis.
- The camera link's own traffic (169.254.x, ≈ 92.8k rows, 19:21:04.87–19:22:19.25, including the reconnect start) is in the raw ETL but excluded from the extract. This is the camera link, not unrelated university traffic.

**Alignment (ETW clock → gateway monotonic clock):**
- Each marker's first trace event falls inside its own connect interval: start 5.09 ms of 5.35 ms; end 3.91 ms of 4.12 ms.
- Drift between start and end −0.001 ms. Millisecond-level alignment is therefore established for this run.

**Analysis** (`tools/analyse_o1_etw_capture.py`): **verdict "INCONCLUSIVE: no holds occurred during the capture"**. No hold, so no per-hold correlation was possible.

**Clean-streaming baseline** (`tools/baseline_o1_etw_connections.py` → `analysis/o1_baseline.json`; observations only):

| Connection | Sends (1332, client / server side) | Longest send gap in the steady window | Gaps > 100 ms | Gaps > 250 ms |
|---|---|---|---|---|
| Publisher, left | 50,607 / 50,608 | 110.0 ms | 2 | 0 |
| Publisher, right | 50,603 / 50,604 | 106.7 ms | 3 | 0 |
| Reader, left | 44,739 / 44,737 | 111.7 ms | 2 | 0 |
| Reader, right | 44,751 / 44,750 | 107.4 ms | 3 | 0 |

- **Observed:** no retransmission-type events (1186 / 1187 / 1351 / 1584) and no zero-window probes (1102) on any of the eight instances. Maximum RTO 1,000 ms (client sides) and 300 ms (MediaMTX sides).
- **Observed:** 4 drop events (1214) on 8554, raw reason text "Received RST (subreason 0)". Not interpreted further. Their likely context is teardown: Unity's readers were "forcibly closed", and the gateway's connections "aborted", per `mediamtx.log`.
- **Inference (not proof):** the longest gaps (≈ 107–112 ms) appear on the publisher and on the matching reader at the same size. They agree with Unity's 116.6 ms maximum interval, which points to source cadence (camera or gateway) rather than a loopback hold.
- **Unresolved:** O1's cause; whether data-retransmission and zero-window events would appear during a hold. Neither occurred here, so both are still unverified on real traffic.

**Retention and clean-up:**
- `raw/o1.etl` retained locally. SHA-256 `702180c8…499db0` (`raw_sha256.txt`), re-verified before the CSV was deleted.
- The intermediate CSV (`decoded/o1_decoded.csv`, 3,107 MB, 3,155 s to decode) was deleted after the extract, alignment and analysis were validated.
- Retained: `extract/` (extract.jsonl.gz 69 MB, connections.json, extract_summary.json), `analysis/` (o1_capture_analysis.json, o1_baseline.json), markers, handshake, capture_times.json, trace_size_check.json, o1_summary.txt and logman_query_before_stop.txt.
- **After the run:** no tracerpt, logman, MediaMTX, Python, Unity, runner or capture processes; nothing listening on 8554. The unelevated `logman query -ets` lists no sessions, but it cannot see elevated sessions; the authoritative check is the wrapper's elevated `session_after_stop: 0`.
- No transport, security, network or software changes. Nothing uploaded.

### 13.41 Commissioning viewing mode: recovered, completed and verified offline (16 Nov 2026; UNCOMMITTED; no live run)

**Recovery:** the 13 Nov session that started this work crashed (authentication 403) after writing the four `Assets/Phase2/Commissioning` source files; they had never been compiled. Unity remained at `d7371d6` with only these changes uncommitted. No leftover project processes were found.

**Scope (researcher, 13 Nov, unchanged):** live Camera A only; free inspection (zoom/pan); the Site Window's truthful video status and stale dimming; a bounded launch with a remaining-time indicator and a clean, confirmed exit; its own evidence; labelled as commissioning, not participant data. No trials, SAGAT, confidence prompts, simulated robot actions or robot control. Synthetic Camera B is not offered. The S3/S4 scenes and builds are unchanged.

**Made:**
- `Commissioning/Model` (pure C#): `CommissioningClock` (clamped to 600 s launch / 525 s view), `VideoLabel` (Site Window wording), `CommissioningSession` (logged inputs, confirmed end, time limit, continuity).
- `Commissioning/Unity`: `CommissioningView`, `CommissioningUi`, `CommissioningScript` (23 scripted checks through real pointer events).
- `Editor/CommissioningBuild.cs` -> scene `Scenes/Commissioning_View.unity`, player `Builds/Commissioning/CommissioningView.exe`.
- `VideoStatus.cs`: receiver stops prefixed `cv_` count as deliberate (like `s3_`/`s4_`).
- `run_stage2.ps1 -Player Commissioning` (gateway, guards and transport unchanged; 120 s / PreviewSeconds <= 85, or `-ExtendedTest` up to the same hard 600 s, PreviewSeconds <= GatewaySeconds - 75); `analyse_stage2.py --player commissioning --cv-out` (S6_commissioning_live_view). Originals in `backups/20261116_commissioning_recovery_pre_edit/`.
- Corrections found while verifying: the start-up wait was counted as an interruption (now `first_image_after_s`; the interval starts on the first valid view, as in §13.32); screenshots were not written from a relative path (now absolute).

**Results (offline):** EditMode 211/211 (198 baseline + 13 new) after regenerating the C09 clock reference (stale after reboot). Player scripted run on recorded Camera A E1: 23/23 checks PASS, first image 1.5 s, the injected 1.4 s freeze shown as "Image not current" then "Video interrupted", dimmed, one interruption recorded, receiver stopped as `cv_operator_end` (state stopped, not failed). Launcher `-PlanOnly`: two valid plans; three correct refusals (85 s limit without extended mode; 75 s reserve; M1 still refuses extended mode). Analyser: M1 regression identical criteria; commissioning branch PASS on a planned end, FAIL on an unplanned end (scratch copies only).

**Not tested:** live Camera A in this view; the runner's `-Player Commissioning` launch beyond `-PlanOnly`; Quest. O1 holds will still show as "Image not current"/"Video interrupted" and are recorded, not repaired.

**Backup:** `backups/20261116_commissioning_view/` (SHA256SUMS.txt).

**COROL (source inspected read-only, `lab_digital_twin` 55cfb61):** the researcher controls the twin and the real robot over LAN with this repository; the Albert sample is simulated, but this does not make COROL simulation-only. The 13 Nov Dashboard load/play proposal is withdrawn. Adapter proposal in the 16 Nov session; not implemented.

### 13.42 Commissioning view: live Camera A check (17 Nov 2026, 13:12–13:21; approved; committed `6d65e06`)

**Command (approved; Camera A only, Wi-Fi on):** `camera_gateway\tools\run_stage2.ps1 -Player Commissioning -NetworkScope EthernetScoped -ExtendedTest -GatewaySeconds 300 -PreviewSeconds 180`. Two runs were made. The second checked inputs that the first did not exercise.

| Run | Viewing | Analyser | Inputs exercised |
|---|---|---|---|
| `results/stage2_runner_20261117_131213` | 106 s, operator end | S1–S11 PASS (calibration unchanged; S6 commissioning live view PASS; S11 cleanup PASS) | Zoom buttons (6), drag pan (29 accepted, 1 rejected `at_edge`), Reset, 3 screenshots (button), End → Keep viewing → End → End now |
| `results/stage2_runner_20261117_131833` | 55 s, operator end | S1–S11 PASS | Zoom buttons, pan, Reset, 2 screenshots (one by F12, *operator-reported*), the same end sequence |

- **First image:** after 2.4 s in run 1. The status showed "Live" (`current`) at the start, the end and in every screenshot. Screenshots were saved in about 0.1 s each, 0.78–0.81 MB.
- **Receiver:** stopped as `cv_operator_end` (deliberate, state `stopped`, not failed). Unity exit code 0. No leftover processes and no abort file. Wi-Fi probe 29/29 and 16/16 HTTPS 200.
- **Continuity in run 1:** 98.3 of 103.9 s valid. 10 not-current episodes: 5 brief (17–35 ms) and 5 of 0.6–1.9 s. These are recorded as O1-type stalls and not diagnosed.
- **O2:** one "Device crashed, but no crash dump could be extracted" line per run, during the post-stop reconnect, as before.
- **Not live-tested:** click-to-zoom on the image. No `view_zoom_at` event occurred in either run because the operator used the buttons. It is verified offline only.
- **Logging gap:** F12 and the button both log `ui_click save_screenshot`, so the source of a screenshot can't be told from the log.
- **Cosmetic:** the on-screen evidence path loses the "r" of `\results` at its line wrap. The paths on disk are correct.

**Commit:** Unity `6d65e06`, local only, not pushed. **Backup:** `backups/20261117_commissioning_live_check/` (SHA256SUMS.txt), covering the gateway source, `corol_link/` and this checkpoint. corol_link 37/37 tests pass offline.

### 13.43 Unity → COROL digital twin, simulation only (17 Nov 2026; researcher-authorised; visual walkthrough passed; Unity committed `04e6fd0`)

**Scope (researcher, 17 Nov):** stop searching for the old launch commands. Build the smallest end-to-end simulation integration from the source:
- Unity triggers one named simulated operation through COROL;
- the movement is seen in COROL's twin;
- Unity receives truthful feedback.

No physical robot, rail or gripper commands. COROL is to be changed only on the researcher's own branch, and only if needed. It was not needed: COROL `55cfb61` is unchanged, and its `git status --ignored` is empty.

**Made (`corol_sim/`; full detail in `corol_sim/README.md`):**
- **Environment:** a dedicated `corol_sim/.venv` (Python 3.13.17) with fastapi 0.163.1, uvicorn 0.54.0, pydantic 2.14.3 and numpy 2.5.5. Deliberately no `ur_rtde`. The camera environments were not touched.
- **`twin_sim_launch.py`:** COROL's `server.py`, unchanged, in a guarded process:
  - loopback-only sockets and stub `rtde_*` modules, self-tested on TEST-NET-1;
  - the real-gripper pass-through goes to an explicit loopback fake (503);
  - physical routes refused with 403 (`/api/state`, `POST /api/sync/live`, `/api/execute`, jog, release, dashboard, stops, `/api/robot/tcp`, `/api/gripper/*`);
  - bound to 127.0.0.1;
  - simulator state kept outside the checkout;
  - no bytecode written into the checkout.
- **`routine_host.py`:** loopback HTTP. It runs one named step through `corol_link/requests_ledger.run_step`, unchanged: duplicate protection, UNKNOWN_OUTCOME blocks until operator resolution, nothing replayed.
- **`twin_steps.py`:** two named steps built from COROL's own example functions (move, wait and verify) and its pose file (placeholder; not approved for physical use):
  - `albert_start_pose`: the arm goes upright, then the rail moves to 4700 mm;
  - `albert_enter_regolight`: the arm goes upright, the rail moves to 2532 mm and the gripper opens to 110 mm.
- **Integration point:** COROL's own `robot_sim` path, with Remote mode as the ownership rule. There is no `robot.Robot`, no `/api/execute`, and no competition with SharedRobots/ControlPool.
- **Unity:** `Assets/Phase2/CorolSim` (model, view, 12 EditMode tests), its own scene and player `Builds/CorolSim/CorolSimControl.exe`. It shows:
  - accepted, running (with sub-step), completed (verified in the twin), failed, rejected, unknown, and "no reply (not resent)";
  - the live twin state.
  It is labelled simulation only and not the participant experiment.

**Results:**
- corol_sim tests 16/16; corol_link 37/37.
- Unity EditMode 223/223 (211 existing + 12 new; C09 clock reference regenerated after the reboot). Player build succeeded.
- `corol_sim/e2e_check.py` 8/8 PASS (`corol_sim/runs/e2e_20261117_135811`):
  - E2: Remote mode off → definite FAILED, twin unchanged;
  - E3: Unity → COMPLETED, twin arm 0 → upright, rail 0 → 2532 mm, gripper 0 → 55 counts;
  - E4: duplicate id not re-run;
  - E5: busy rejected;
  - E6: host killed while the rail moved → UNKNOWN_OUTCOME, everything blocked until resolved, never replayed;
  - E7: start pose completed;
  - E8: 0 blocked connection attempts and 0 fake-gripper hits.
- First attempt: robot_sim's `track.init()` feedback check rejects a fresh simulator at exactly 0.0 mm. This is handled only in that case, logged and documented.

**Not verified:** any physical behaviour.

**Still undecided (unchanged from the source audit):** control handover versus a routine inside the server; stop semantics (no combined stop is authorised).

**Visual walkthrough (17 Nov 2026, 15:31–15:34; researcher at the screen) — PASSED *(user-reported)*.** The researcher watched the browser twin move. Evidence: `corol_sim/runs/corolsim_20261117_153146`, `host_20261117_153139`, `twin_20261117_153137`. Five Unity requests, all COMPLETED, none failed, refused or unknown; Remote mode turned on at t = 33 s; 0 blocked connection attempts:
1. `albert_enter_regolight` → "already in position (twin unchanged)";
2. `albert_start_pose` → verified, rail +2168 mm;
3. `albert_start_pose` → "already in position";
4. `albert_enter_regolight` → verified, rail −2168 mm;
5. `albert_start_pose` → verified, rail +2168 mm.

Differences from the README walkthrough, taken from the logs (the researcher reported no further differences):
- **Step 2 of the README walkthrough said the first `albert_enter_regolight` would show "verified in the twin"; it showed "already in position".** The twin restores its last pose from `corol_sim/state/sim_state.json`, and the e2e run had left it at the RegoLight position (rail 2532 mm, gripper open). The README now notes this.
- **`host_events.jsonl` writes the `ledger_accepted/started/completed` events only when the step returns.** Unity received HTTP 202/STARTED at once, and the ledger file itself is correct, so this is only a logging-order quirk.

**Committed** as Unity `04e6fd0` (local, not pushed). The rest of `corol_sim/` is outside git and backed up in `backups/20261117_corol_sim_baseline/` with SHA-256 hashes.

### 13.44 COROL Albert pick-and-place script: inspection and one guarded run (17 Nov 2026, 16:03; analysis only, no integration)

CRATER visit postponed. Next goal: one experiment-like S4 trial against the twin. COROL's `Albert/albert_lantern_regolight_pick_place_sim.py`, unmodified, was run once inside the sim guard (scratchpad runner, `corol_sim` twin launch, own state copy). Evidence: `corol_sim/runs/albert_full_20261117_160301`.
- **Result:** PASS. 6 pick-and-places, 3 RegoLight and 3 Lunar Lantern, in 154 s of timed run.
- **Isolation:** 0 blocked connections, 0 fake-gripper hits, 0 refused routes.
- **Twin state:** `/api/sim/state` holds only robot fields (`q`, `tcp_pose`, `moving`, `freedrive`, `track_mm`, `track_v`) plus the gripper status. There is no object state.
- **Blocks are not carried.** The script's own docstring says "the twin does not carry the block — only the fingers move", and robot_sim says "nothing in the sim to grasp". The layout GLB with the bricks (`albert_phase2_setup_lite.glb`) is missing from the checkout. Collisions are drawn only in the browser and do not stop motion.
- **Not observed visually:** no browser was open.

Full findings and the proposed first trial are in the 17 Nov chat report.

### 13.45 Phase 2 scene in the twin + ONE-PLACEMENT S4 rehearsal with a scripted RegoLight brick (17 Nov 2026, evening; UNCOMMITTED for review)

**Scope (researcher):** load the new environment GLB into the guarded twin and record the alignment; give a visual checkpoint; complete the one-placement S4 integration; prepare one RegoLight brick for scripted pickup, transport, release and retreat through the existing routine host. Attach and release happen at operation milestones and reset restores the brick. Scripted, not physics. Hardware stays disabled; one nominal placement; no deliberate errors or recovery.

**Scene:**
- `U:\…\GLB\PHASE 2 digital twin import.glb` was copied, byte-identical, to `corol_sim/assets/phase2_digital_twin_import.glb` (SHA-256 `f11205e6…b333`; original untouched).
- **Alignment (recorded):** position `[0.28897, 0.165, 5.44153]`, rotation `[0, -90, 0]` deg, scale 1, i.e. world = (0.28897 − g_z, 0.165 + g_y, 5.44153 + g_x). This is COROL's own transform for its earlier layout, which shares the Blender frame.
- **Checks:**
  - metres;
  - floor at y = 0.000;
  - RegoLight on the rail-mm < 4700 side;
  - COROL's placeholder pick-1 grasp point lands inside brick 018 at its mid-height;
  - browser and server TCP agree to 0.42 mm.
- COROL is unchanged. The GLB and config are served from `corol_sim`, and the served `index.html` gets one hook line.

**Visual checkpoint** (headless Edge, `corol_sim/runs/scene_probe_20261117_184648/visual/01–04`): overview, RegoLight pickup tray (brick 018 highlighted), build tray, formwork. The formwork has rhombic half-brick "teeth" at both ends and a centring shell between them. The brick is a rhombic dodecahedron.

**Placement (`regolight_place_brick018`):**
- The grasp is across the brick's 90 mm parallel faces (pad centre 10 mm above the brick centre).
- The seat is chosen by an explicit rule and checked against the formwork mesh: (0.732, 0.139, 9.152) m, 0.01 mm penetration, 3 supporting faces, inner side, yaw −34.6°.
- COROL's move, wait and verify functions do the moves; attach and release are reported only after the gripper is confirmed.
- **Result:** seat error 0.024 mm / 0.064°, attach jump 0.000 mm.

**S4 rehearsal:**
- `phase2_s41_corol_rehearsal.json` (status `development_rehearsal`; the validator allows one CDP location for that status only).
- `-s4Corol` / `-s4CorolScript`:
  - the trial reset waits for the twin baseline;
  - the CDP opens only after the verified placement;
  - a failure or unknown outcome ends the trial with no retry;
  - Intervene, recovery and Retry are unavailable (greyed, refused, not remapped);
  - the tag reads "DEVELOPMENT REHEARSAL · SIMULATED DIGITAL TWIN · PLACEHOLDER POSES".
- SAGAT → first commitment → confidence → execution is unchanged.

**Results:**
- `corol_sim/rehearsal_e2e.py` 16/16 (`runs/rehearsal_20261117_193907`); player UI checks 18/18;
- rendered brick: rigid while carried (2.52 m, 0.0 mm drift), stays at the release pose during the retreat, restored at the trial reset (0.098 mm);
- 0 blocked connections, 0 fake-gripper calls, 0 refused routes; COROL clean;
- Unity EditMode 232/232 (C09 reference regenerated after a −3.3 s clock step);
- corol_sim 23/23; corol_link 37/37; earlier `e2e_check.py` 8/8.

**Limits:**
- The S4 plate shows recorded Camera A, which ends before the CDP ("Video unavailable"), so the participant does not see the twin in Unity. Suggestion: point live Camera A at the twin display.
- Scripted objects only.
- The seat rule is inferred from the geometry, so the researcher should confirm the intended slot.
- Placeholder poses and alignment are not surveyed and NOT approved for physical use.

**Note:** I continued past the visual checkpoint without a pause, because the numerical alignment checks agreed. The checkpoint images are available for review.

**ACCEPTED (researcher, 18 Nov 2026):** the scene layout and the chosen receiving seat were reviewed visually and accepted for this simulation rehearsal.

**Scope of that acceptance (recorded 18 Nov 2026 at the researcher's request):** this rehearsal is kept as a HISTORICAL FLOW TEST of the session sequence (trial reset, twin placement, CDP, SAGAT, first commitment, confidence, execution). Its observation and restoration checks BYPASSED valid imagery. In `runs/rehearsal_20261117_193907` (and every run of `phase2_s41_corol_rehearsal.json`, policy `development_override`):
- recorded Camera A had ended before the CDP;
- observation began under `exhausted_recording_development_override`, with 0 ms of valid view;
- restoration accepted an ended recording;
- the first commitment was made on a 28 s-old image.

The acceptance covers the scene layout, the receiving seat and the flow only. It does NOT imply acceptance of visual decision-making on exhausted footage. Visual decisions are first tested under `phase2_s41_corol_viewing.json` (require_live, §13.46). Checkpointed as Unity `37e93f0` (local, not pushed) and `backups/20261118_corol_rehearsal_accepted/` (96 files, SHA-256 verified; no environment or caches).

### 13.46 Viewing rehearsal: site view (Camera A filming a display) + virtual wrist view (18 Nov 2026; UNCOMMITTED for review; offline only)

**Scope (researcher):**
- **Site view:** physical Camera A filming a screen with a fixed overview of the running twin.
- **Wrist view:** a virtual camera near the gripper.
- **Guards and labels:** keep the hardware identity and network guards; record the view role separately from the camera identity; no physical Camera B; label both sources accurately; 2D, not stereo.
- **Gating:** remove the exhausted-footage bypass.
- **Tests:** test offline, including render and simulator loss and stationary vs stalled; then prepare the walkthrough.

**Findings:**
- **COROL cameras:** COROL supports robot-mounted client cameras only. They are rendered off-screen by the viewer at 10 Hz nominal and relayed one at a time via `/api/camera/frame`.
- **Previous rehearsal:** it progressed on exhausted recorded footage. Observation began under `exhausted_recording_development_override` with 0 ms of valid view, restoration accepted an ended recording, and the first commitment was made on a 28 s-old image.
- **Second bypass:** a restoration timeout opened the decision anyway (`view_restoration_unverified`).

**Built:**
- **Wrist camera:** a COROL client camera generated from the editable `corol_sim/assets/virtual_cameras.json`.
- **Frame store:** a per-camera store in the launcher (capture time + simulator age per frame).
- **Renderers:** headless pages (`vcam_render.py`) using a render-only config without colliders, plus an offline fixed site stand-in.
- **Unity source:** `VirtualCameraSource` (an IFeedSource) with `VirtualFrameGate`: absolute age, its own 500 ms freshness limit, and the states streaming / stationary / stalled / simulation_stale.
- **Site Window:** slot A = Site view, slot B = Wrist view; labels "camera filming a display", "rendered virtual camera", "rendered stand-in"; "Current render" instead of "Live". `video_sources.view_roles` records role vs source.
- **Protocol:** `phase2_s41_corol_viewing.json` (require_live). The restoration timeout no longer opens the decision under require_live; development_override is unchanged.
- **Runner:** `run_stage2.ps1 -Player S4CorolViewing` (as S4Demo, with pre-checks for the twin, host and wrist renderer).
- **Launcher:** `start_corol_sim.ps1 -Viewing` (twin, host, wrist renderer, full-screen site display).
- **Long poll:** object state is now long-polled by the viewer. Under load the brick was briefly drawn attached during the retreat (6–36 mm); it is now 0.000 mm.

**Results:**
- `viewing_e2e.py` 15/15 (`corol_sim/runs/viewing_20261118_145940`):
  - simulator loss → both views simulation_stale, and the trial waited until both were current;
  - wrist closure → stalled, then recovered;
  - robot at rest → stationary, still current;
  - site closure at SAGAT → the restoration waited past its timeout, and the decision opened 0.2 s after the view was current again.
- Unity EditMode 245/245 (C09 reference regenerated after a reboot); corol_sim 28/28; corol_link 37/37.
- Regressions: rehearsal_e2e 16/16, e2e_check 8/8. The runner plan-only check passed for S4CorolViewing, and S4Demo and M1 are unchanged.

**Not done:** no live run; Camera A was not connected. Next: the researcher positions Camera A at the site display, then the live walkthrough in corol_sim/README.md.

**Pre-run review (researcher's three questions, 18 Nov):**
1. **Scope:**
   - The **500 ms limit** applies only to rendered virtual sources (`S4Viewing.MakeFeed`, mode virtual). The camera receivers keep 150 ms.
   - The **30 fps cap** is set only under `-s4Viewing`. However, the camera receiver sets `QualitySettings.vSyncCount = 1` when it starts (validated M1 code, unchanged), and Unity ignores `targetFrameRate` under vSync. So in the LIVE configuration (slot A = receiver) the cap has no effect, and Unity runs vSync-limited as in every earlier live Camera A run. The cap is effective only offline (both slots rendered).
   - The **`require_live` restoration change** applies only to protocols with that policy, and only `phase2_s41_corol_viewing.json` uses it.
2. **Frozen overview:**
   - Camera A frames alone are NOT taken as proof of a current twin view. The site display page sends a heartbeat (animation frames, simulator age, visibility) to the twin, and the Site Window gates slot A on it (`SourceGate`; `site_display_gate` records; trial readiness also requires it).
   - **Detected:** page closed, crashed or frozen; not rendering; hidden or minimised; simulator updates lost.
   - **NOT detectable:** monitor off or frozen at the hardware level, window partly covered, an overlay that doesn't stop the page rendering, the camera pointed elsewhere (the image content is not analysed). These are recorded in `video_sources`.
   - **Offline test** (`viewing_e2e.py --site-gate`, 17/17, `runs/viewing_20261118_154807`): closing the display page gated the site view within 1.0 s while its source kept streaming; reopening cleared it within 0.8 s. A first attempt found a recursion (the gate logged through the client context, which reads the gate) that overflowed the stack; fixed by setting the logged state before logging.
3. **Earlier rehearsal:** recorded in §13.45 as a historical flow test whose imagery checks bypassed valid imagery. Its acceptance does not cover visual decision-making on exhausted footage.

**Live viewing trials (18 Nov 2026; researcher as participant; Camera A filming the site display on a second monitor; scoped Ethernet, Camera A only):**
- **Framing:** commissioning view `camera_gateway/results/stage2_runner_20261118_155607`, analysis exit 0.
- **Trial 1, INVALID as a viewing trial** (`stage2_runner_20261118_160216`): the robot did not move. The persistent ledger (`corol_sim/state`) already held the same request ids (`S4-P901-01-…-B1-T1-baseline` / `-RG-P1`) from an earlier session. The host correctly ran nothing (`duplicate_ignored`) but answered with the old COMPLETED records, and Unity accepted them as this trial's execution.
  - **Fixed:** request ids now carry a per-run stamp, and a `duplicate` reply is treated as `DUPLICATE_NOT_EXECUTED` (failure), never as this trial's execution.
  - **Also changed after trial 1 (researcher):** the site display view now comes from the GLB object "regolght site cam" (camera body `Camera.001`, local −Z, as modelled level), pitched 25° down (`pitch_down_deg`), with vfov 54°. The display page no longer shows the wrist camera gizmo. The offline re-check passed 17/17 (`corol_sim/runs/viewing_20261118_161710`).
- **Trial 2, COMPLETED** (`stage2_runner_20261118_162238`, analysis exit 0; researcher: "everything worked well"):
  - **Twin:** a unique-id baseline restored brick 018; the placement was executed (attach 16:24:55, release 16:25:07, brick moved 2523 mm).
  - **Views:** observation, restoration and the first commitment were all on a CURRENT, VISIBLE live site view; no restoration timeout. The observation had 2.9 of 3.0 s valid view; the decision period 25.7 of 27.1 s.
  - **Site-display gate:** it withheld the site view once, for about 2 s (`display_health_unavailable`: no health answer for over 1 s), then cleared.
  - **Wrist view:** 453 frames, median 5.4 fps (minimum 2.4), median age at presentation 92 ms; 2 brief stalls.
  - **Isolation:** 0 blocked, 0 fake-gripper calls, 0 refused; COROL unchanged.
  - **Framing:** the wrist framing was viewed by the researcher; adjustment is still open.

### 13.47 RegoLight development trial: 16 placements on the twin, 2D, two rendered views (18 Nov 2026; UNCOMMITTED for review; simulation only)

**Scope (researcher; approved specification Methodology v18(3) / Appendices v6(3)):** one complete RegoLight / 2D development trial, extending the existing S4 interface, routine host, ledger and COROL simulator. Physical robot, gripper and cameras stay disconnected. Site view = fixed external virtual camera; wrist view = robot-attached virtual camera. Checkpoint before editing (dfc2e70 + `backups/20261118_viewing_checkpoint`).

**Layout (researcher, 18 Nov):** sketch (P = preinstalled; numbers = order) and the exported model `PHASE 2 digital twin import- only regolight built.glb` (36 bricks, 9 rows × 4 lanes; copied unchanged to `corol_sim/assets/phase2_regolight_built_layout.glb`, SHA-256 `7eae1646…aa48`). The sketch numbers **16** placements; the researcher chose 16 "for now" (spec said 15; indices configurable).
- Rows 1–2 and 7–9 preinstalled (20); row 3 = 1–4, row 4 = 5–8, row 6 = 9–12, ridge row 5 = 13–16 (closes the gable layer last).
- **Alignment:** the export sits 20 mm below the scene formwork (rows 1 and 9 penetrated 19.9 mm). One recorded uniform shift (−1.4, +20.0, −1.2 mm), anchoring built brick .001 on the ACCEPTED seat, fixes it: 0 mm brick–brick overlap, max formwork penetration 0.8 mm (tol 1 mm), all 36 cells face-connected at exactly 90.0 mm. No brick moved individually.
- An earlier lattice-only proposal (`assembly_lattice.py`, `runs/assembly_preview_20261118_170817`) is superseded by the researcher's layout.

**Implementation (all configurable):**
- `assembly_manifest.py` → `plans/regolight_assembly_manifest.json` (brick, pickup pose, nominal receiving pose, neighbours, contacts; preinstalled separately; nearest-16 tray bricks picked).
- `plans/regolight_trial_config.json`: P10 prescribed variation **8° about world +Y through the brick centre** (anticlockwise from above), then the smallest shift away from its present face neighbours that clears them (6.0 mm; a vertical lift does not clear on the 30° slope). Nominal, prescribed and realised poses recorded separately; no snap after Allow.
- `trial_plan.py`, `trial_steps.py` (70 host steps), `scene_objects.baseline()` + `/api/phase2/objects/baseline`.
- Unity: `SimulatedBackendExternal.cs` (accepted recover / nudge / place-and-release / Retry executed by the host; refusal = nothing changed; other failure / unknown = uncertain, authorisation ends, reconciliation required, host ledger resolved first; twin-measured pose replaces the settle model); `S4CorolTrial.cs` (bridge, `-s3ASiteRendered`, scripted run); protocol `phase2_s41_corol_regolight_trial.json` (16 placements; CDPs early = P05, middle = P10 (SAGAT), late = P14 inactive; 10 s observation at every formal CDP; RG-2 items, familiarisation text and confidence prompt/anchors verbatim; scoring unvalidated, no answer key); confidence anchors in the UI; familiarisation phase; SAGAT item ids, applicability flag and freeze reference recorded.

**Verification:**
- Python 42/42 (`tests/test_trial.py` 13 new). Unity EditMode 253/253 (`CorolTrialTests` 6 new).
- Twin-only e2e `trial_twin_e2e.py` 15/15 (`corol_sim/runs/trial_twin_20261118_205109`): baseline, 16 placements, recover + nudge + Retry at P05, P10 rotation realised 8.0°, individual rotation nudges, nudge beyond the 12° limit refused before motion, controlled place-release, duplicate id runs nothing, placement replay refused, no unknown outcomes.
- **Real player e2e `trial_e2e.py` 11/11 with 41/41 UI checks** (`corol_sim/runs/trial_20261118_212258`; player `test_results/ai2_s4_20261118_212316_win64player`): both rendered views streaming (~10 fps, 960×600); unscheduled Inspect during P03 (acknowledged immediately, held at the safe state, view only); Intervene hold during P05 merged into the CDP; Allow + confidence at P05; unscheduled Intervene during P07 → recovery → nudge → Retry (no confidence); P10: 10 s observation → RG-2 probe (imagery hidden) → restored current view → Inspect (wrist 3×) → Intervene → Recover → confidence → facilitator review / grasp / authorisation → 4 × −2° and 2 translation nudges → place-release → reassess → Allow; P14 no cue; 16 placements each once; final assembly within 0.1 mm of nominal except P10 (corrected to 0.003°, 0.3 mm horizontally, 1.6 mm low after lowering to first contact). Trial duration 10.0 min (target ~7.5 min; twin placements ~33 s each).
- **Failed run kept separately** (`corol_sim/runs/trial_20261118_210809`, 9/11): the text lint flagged the approved RG-2 wording ("corrective", "correction"), now exempted as verbatim instrument text; and a real mouse click on the player window (hover trail Allow → Inspect at P15) created a third unscheduled episode, handled correctly by the system; the script now separates scripted holds from real pointer input.

**Limits:** scripted objects (no contact physics): an uncorrected P10 leaves later nominal bricks overlapping it (planned: P11 7.0 mm, P14 6.3 mm, P15 9.4 mm); gripper finger clearance against row neighbours not modelled; no vertical nudge axis; from the fixed site camera the formwork is small, so the 8° offset is clearer through Inspect zoom or the wrist view; the 10 s observation applies at both formal CDPs (blinding of the probe placement).

### 13.48 Checkpoint, fully nominal configuration, grasp-teaching route, site camera (18–19 Nov 2026; new work UNCOMMITTED; simulation only)

**Checkpoint:** after the researcher's manual trial (S4-P901-01, all integrity checks pass), the 13.47 version was committed locally as `bd662b9`, tag `regolight-trial-dev-v1` (no remote, nothing pushed). The backup is `backups/20261118_checkpoint_regolight_trial_dev_v1`: a git bundle, the simulator source and the manual-trial evidence, 88 files, SHA-256 verified. Its limitations and its variation scenario are kept.

**Nominal (researcher: no further variations).**
- Configuration `plans/regolight_trial_config_nominal.json`: zero offset at all 16 placements, stated explicitly; a non-zero value is refused at load. It is the host's default. The variation configuration is unchanged (SHA-256 `cdf8c039…`) and used only when selected with `-TrialConfig variation_rgdev_v1`.
- Protocol `phase2_s41_corol_regolight_nominal.json` (scenario `RG-TRIAL-NOMINAL`), generated from the committed variation protocol. CDPs at 5 and 10, SAGAT at 10, inactive 14, and the confidence wording and order are unchanged.
- The player refuses a trial on a twin whose configuration or layout version differs from the protocol's.
- 16 placements are kept, against about 15 in the planning example: the CDP positions are the same and there is one extra placement after the inactive location.

**Contact and overlap rules.**
- `place_release` lowers the held brick, nudges included, straight down in 0.5 mm steps. It is tested against the formwork mesh samples and every brick present, and released at the last step with penetration ≤ 1 mm, searching to the hold height + 20 mm. Only the height changes.
- No valid contact, or an overlap already at the hold pose: **refused before motion**. Before this change, the brick was released 20 mm below the hold height.
- Every placement is checked for obstruction before motion and for overlap after release. An obstructed receiving pose is refused before motion; an overlap after release fails the step, and the brick becomes uncertain. Commanded and realised poses are recorded separately, and nothing is snapped or moved.

**Grasp review and teaching.**
- `grasp_review.py`: the current side grasp makes the left finger enter the row neighbour placed before it by **8.1 mm on the descent and 15.8 mm when opening, at 12 of 16 placements**. Only the first brick of each row is clear.
- Teaching route `teach.py` and panel `/phase2/teach`, with exclusive ownership: a lease is acquired only when the host is idle; Remote mode goes off, so COROL and the host refuse every routine command. Viewer jog and the gripper work only under the lease. Hardware routes and `sim_guard` are unchanged, and the TCP is never changed.
- Saved poses and the brick-to-gripper transform record the frames and versions (`teach/taught_items.json` plus the append-only history).
- One-brick staged review steps (`review_approach` … `review_retreat`) use only the selected taught grasp, at one placement.
- New finger model: still waiting on the researcher for the asset information.

**Site camera.**
- The obstruction was the GLB camera body `Camera.001`: the old optical centre lay 5–9 cm inside it, with a double-sided material, and the tripod head `regolght site cam` was visible below.
- New explicit pose `site_pose_v2`: position (1.75, 1.85, 10.4), looking at (0.80, 0.12, 8.15). The build tray is in the foreground, the pickup tray behind it, the robot in between, and the nearest geometry is 2.0 m away.
- No scene geometry was hidden. The GLB tripod is not moved, and the physical-camera display page is unchanged.
- Before and after views: `corol_sim/runs/site_camera_preview_20261118_231134` and `_231329`.

**Bugs fixed.**
- `scene_objects.mat_rotvec` near a half turn: a taught grasp became a target 5.4° off. It now uses quaternions, and every target is round-trip checked before motion.
- The manifest's 6-decimal rotations are re-orthonormalised (the 0.064° measurement floor).
- Final checks wait for the twin to report the arm stopped.

**Verification.**
- `teach_e2e.py` 12/12.
- `nominal_twin_check.py` 6/6 with the current grasp (interim): 517.5 s nominal execution, mean 32.3 s per placement.
- `trial_twin_e2e.py` 16/16 (variation; P11, P14 and P15 now refused before motion).
- Real player `trial_e2e.py` 11/11 with 41/41 UI checks on spare ports (`runs/trial_20261119_002452`). The failed attempt `runs/trial_20261119_001616` (settling race) is kept.
- Python 52/52; Unity EditMode 255/255.
- Timing of the manual trial (`trial_timing.py`): 738.9 s, of which nominal execution 523.6 s.

**Note:** the twin, host and renderers from the manual trial were still running on 8080/8095 and were not stopped. All new checks used spare ports. Before this was noticed, about 15 preview frames for `site` were posted to that twin's camera store after the trial had ended.

## Evidence

All files are in [`results/`](results/). Timestamps are local time, 3 Nov 2026, taken from the filenames and the files' internal timestamps.

| Time | File(s) | What it shows |
|---|---|---|
| 18:20 | [env_check_20261103_182106.json](results/env_check_20261103_182106.json) | Python, DepthAI, OpenCV and NumPy versions; v3 API availability (`XLinkOut` absent, as expected for v3) |
| 18:24:18 | [net_check_20261103_182418.txt](results/net_check_20261103_182418.txt) | Ethernet 4 link, laptop IP, Camera A ping and TCP 11490 |
| 18:24:45 | [discover_20261103_182445.json](results/discover_20261103_182445.json), [.log](results/discover_20261103_182445.log) | Camera A direct connection and full device record |
| 18:24:45 | [calibration_user_19443010B14C872F00_20261103_182445.json](results/calibration_user_19443010B14C872F00_20261103_182445.json), [calibration_factory_19443010B14C872F00_20261103_182445.json](results/calibration_factory_19443010B14C872F00_20261103_182445.json) | Camera A calibration (read-only copies) |
| 18:25:07 | [discover_20261103_182507.json](results/discover_20261103_182507.json), [.log](results/discover_20261103_182507.log) | Camera A broadcast discovery |
| 18:33:18 | [discover_20261103_183318.json](results/discover_20261103_183318.json), [.log](results/discover_20261103_183318.log) | Failed connection attempt to `.222` (see §4) |
| 18:33:35 | [discover_20261103_183335.json](results/discover_20261103_183335.json), [.log](results/discover_20261103_183335.log) | Camera B direct connection and full device record |
| 18:33:35 | [calibration_user_194430108183F12E00_20261103_183335.json](results/calibration_user_194430108183F12E00_20261103_183335.json), [calibration_factory_194430108183F12E00_20261103_183335.json](results/calibration_factory_194430108183F12E00_20261103_183335.json) | Camera B calibration (read-only copies) |
| 18:33:53 | [discover_20261103_183353.json](results/discover_20261103_183353.json), [.log](results/discover_20261103_183353.log) | Camera B broadcast discovery |

**4 November 2026** (see §6):

| Time | File(s) | What it shows |
|---|---|---|
| 14:05:51 | [net_check_20261104_140551.txt](results/net_check_20261104_140551.txt) | `.222` ping/TCP, both attached |
| 14:06:11 | [net_check_20261104_140611.txt](results/net_check_20261104_140611.txt) | `.223` ping/TCP, both attached |
| 14:06:26 | [discover_20261104_140626.json](results/discover_20261104_140626.json), [.log](results/discover_20261104_140626.log) | Broadcast: both cameras found |
| 14:06:42 | [discover_20261104_140642.json](results/discover_20261104_140642.json), [.log](results/discover_20261104_140642.log) | Camera A: search-stage failure |
| 14:07:04 | [discover_20261104_140704.json](results/discover_20261104_140704.json), [.log](results/discover_20261104_140704.log), [calibration_user](results/calibration_user_194430108183F12E00_20261104_140704.json), [calibration_factory](results/calibration_factory_194430108183F12E00_20261104_140704.json) | Camera B connected |
| 14:07:27 | [discover_20261104_140727.json](results/discover_20261104_140727.json), [.log](results/discover_20261104_140727.log) | Camera A: search-stage failure |
| 14:10:17 | [discover_20261104_141017.json](results/discover_20261104_141017.json), [.log](results/discover_20261104_141017.log), [calibration_user](results/calibration_user_19443010B14C872F00_20261104_141017.json), [calibration_factory](results/calibration_factory_19443010B14C872F00_20261104_141017.json) | Camera A connected (B reportedly disconnected) |
| 14:12:38 | [discover_20261104_141238.json](results/discover_20261104_141238.json), [.log](results/discover_20261104_141238.log) | `.222` target: failure after booting |
| 14:13:17 | [discover_20261104_141317.json](results/discover_20261104_141317.json), [.log](results/discover_20261104_141317.log), [calibration_user](results/calibration_user_194430108183F12E00_20261104_141317.json), [calibration_factory](results/calibration_factory_194430108183F12E00_20261104_141317.json) | Camera B connected; crash dump collected |
| 14:13:26 | `%LOCALAPPDATA%\depthai\cache\crashdumps\4a62e2b290e16f4d3f36b0b4df9490a16aea7229\crash_dump_2026-11-04_14_13_26.tar.gz` (outside the workspace; left in place, unmodified) | Camera B firmware crash dump (§6.2) |
| 14:38:28 | [discover_20261104_143828.json](results/discover_20261104_143828.json), [.log](results/discover_20261104_143828.log), [calibration_user](results/calibration_user_19443010B14C872F00_20261104_143828.json), [calibration_factory](results/calibration_factory_19443010B14C872F00_20261104_143828.json) | Camera A connected with both attached, after the port swap (§6.7) |
| 14:40:11 | [discover_20261104_144011.json](results/discover_20261104_144011.json), [.log](results/discover_20261104_144011.log), [calibration_user](results/calibration_user_194430108183F12E00_20261104_144011.json), [calibration_factory](results/calibration_factory_194430108183F12E00_20261104_144011.json) | Camera B connected with both attached; no crash dump (§6.7) |
| 14:55:27 | [discover_20261104_145527.json](results/discover_20261104_145527.json), [.log](results/discover_20261104_145527.log) | Verified concurrent connection of both cameras, 10 s hold, `RESULT: PASS` (§6.9) |
| 15:22:36 | [stereo_20261104_152236_19443010B14C872F00/](results/stereo_20261104_152236_19443010B14C872F00/report.json) (report, capture.log, pairs.csv, 15 PNGs, calibration copy) | Camera A capture 1: 200 pairs, 1 gap; FAIL (verification defect) (§7.5) |
| 15:23:31 | [stereo_20261104_152331_19443010B14C872F00/](results/stereo_20261104_152331_19443010B14C872F00/report.json) (as above) | Camera A capture 2: 200 pairs, no gaps; FAIL (verification defect) (§7.5) |
| 15:37:12 | [calibration_check_20261104_153712_19443010B14C872F00/](results/calibration_check_20261104_153712_19443010B14C872F00/report.json) | Camera A read-only calibration check: PASS (§7.8) |
| 15:37:49 | [stereo_20261104_153749_19443010B14C872F00/](results/stereo_20261104_153749_19443010B14C872F00/report.json) | Camera A capture 3: 200 pairs, 6 frames missing; PASS (§7.8) |
| 15:40:17 | [calibration_check_20261104_154017_194430108183F12E00/](results/calibration_check_20261104_154017_194430108183F12E00/report.json) | Camera B read-only calibration check: PASS (§7.8) |
| 15:40:34 | [stereo_20261104_154034_194430108183F12E00/](results/stereo_20261104_154034_194430108183F12E00/report.json) | Camera B capture: 200 pairs, none missing; PASS (§7.8) |
| 15:56:03 | [stereo_20261104_155603_19443010B14C872F00/](results/stereo_20261104_155603_19443010B14C872F00/report.json) | Unintended run during argument checks: refused on Wi-Fi before discovery; no camera contacted (§8.1) |
| 16:00:06 | [D1_A_sync](results/stereo_20261104_160006_19443010B14C872F00_D1_A_sync/report.json) | 1,200 pairs, 9 missing (one 685 ms stall) (§9) |
| 16:02:07 | [D2_B_sync](results/stereo_20261104_160207_194430108183F12E00_D2_B_sync/report.json) | 1,200 pairs, 0 missing |
| 16:08:15 | [D3_A_sync](results/stereo_20261104_160815_19443010B14C872F00_D3_A_sync/report.json) | 1,200 pairs, 0 missing |
| 16:10:25 | [D4_B_sync](results/stereo_20261104_161025_194430108183F12E00_D4_B_sync/report.json) | 1,200 pairs, 4 missing (one 568 ms stall) |
| 16:15:32 | [D5_A_hostseq](results/stereo_20261104_161532_19443010B14C872F00_D5_A_hostseq/report.json) | 1,200 pairs, 0 missing, per-sensor continuous |
| 16:18:04 | [D6_B_hostseq](results/stereo_20261104_161804_194430108183F12E00_D6_B_hostseq/report.json) | 1,200 pairs, 0 missing, per-sensor continuous |
| 16:23:21 | [D7_A_sync_preview](results/stereo_20261104_162321_19443010B14C872F00_D7_A_sync_preview/report.json) | 1,200 pairs, 0 missing; preview cost 6.05 ms/pair |
| 16:41:56 | [stage_e_offline_20261104_164156_A_D3](results/stage_e_offline_20261104_164156_A_D3/geometry_offline.json) | Offline host rectification of D3 raw pairs, Camera A (§10.2) |
| 16:42:00 | [stage_e_offline_20261104_164200_B_D2](results/stage_e_offline_20261104_164200_B_D2/geometry_offline.json) | Offline host rectification of D2 raw pairs, Camera B (§10.2) |
| 17:03:26 | [E1_A_default](results/rectify_20261104_170326_19443010B14C872F00_E1_A_default/report.json) | 45 groups, PASS; distortion correction on, alpha default (§11) |
| 17:04:09 | [E2_B_default](results/rectify_20261104_170409_194430108183F12E00_E2_B_default/report.json) | 45 groups, PASS; distortion correction on, alpha default |
| 17:06:59 | [E3_A_alpha0](results/rectify_20261104_170659_19443010B14C872F00_E3_A_alpha0/report.json) | 45 groups, PASS; alpha 0 |
| 17:07:52 | [E4_B_alpha0](results/rectify_20261104_170752_194430108183F12E00_E4_B_alpha0/report.json) | 45 groups, PASS; alpha 0 (non-square output) |
| 17:10:00 | [E5_A_dc_auto](results/rectify_20261104_171000_19443010B14C872F00_E5_A_dc_auto/report.json) | 45 groups, PASS; distortion correction AUTO (identical to E1) |
| 17:15:58 | [stage_e_analysis_20261104_171558](results/stage_e_analysis_20261104_171558/analysis.json) | Offline re-analysis: dy model, outliers, measured borders, model check, cross-run mapping (§11) |
| 17:28 | [epipolar_analysis_20261104_scene1_baseline](results/epipolar_analysis_20261104_scene1_baseline/analysis.json) | Scene-1 baseline for the cross-scene comparison: model with 95% intervals, coverage, crop check, in-sample corrections (§12.2) |
| 17:30:11 | [coverage_markers_20261104_173011_140mm](results/coverage_markers_20261104_173011_140mm/README.txt) | Printable ArUco markers 0–7 (140 mm) for the CRATER coverage check (§12.5) |
| — | none | MAC checks and port swap: user-reported, no transcript saved |

---

## Development checkpoint

| Milestone | Status |
|---|---|
| Task 01: Audit recovered Unity project | Completed |
| Task 02: Audit original Side Quest camera sender | Completed |
| Task 03 Stage A: Python and DepthAI environment preparation | Completed |
| Task 03 Stage B: Individual camera discovery | Completed (both cameras) |
| Task 03 Stage B: Both cameras on one network | **Completed 4 Nov.** Broadcast discovery of both, sequential connections with both attached (14:38, 14:40), and **verified concurrent connection held 10 s (14:55, `RESULT: PASS`)** (§6.9). The earlier address-resolution failures cleared after a switch-port swap; their root cause is not confirmed (§6.5–6.7). |
| Task 03 Stage C: Stereo image acquisition | **Initial functional validation complete for both cameras (4 Nov).** Camera A at 15:37 and Camera B at 15:40: 200 synchronised native 1280 × 800 pairs each, `PASS`, calibration unchanged (§7.8). **Not established:** loss-free continuity. Camera A missed frames in 2 of 3 runs; Camera B had 0 missing in its one run (§7.8–7.9). The two 15:22/15:23 runs remain recorded as FAIL (§7.5). |
| Task 03 Stage D: Synchronisation and frame-continuity analysis | **Completed 4 Nov; analysis complete (D1–D7, all PASS).** Left/right synchronisation verified: 8,400 pairs, equal sequence numbers, \|L–R\| ≤ 0.03 ms. Continuity characterised: delivery stalls about 2.7 per minute, frames lost only when the backlog exceeds about 6–7 frames (13 of 8,413 frames; both cameras). **Root cause of the stalls not established** (§9). |
| Task 03 Stage E: Rectification and visual checks | **E1–E5 complete and analysed (§11).** **Provisional configuration approved by the researcher** (§12.1): explicit distortion correction, default alpha, Camera A crop x 39–1276 / y 6–775, Camera B uncropped at 97.1° × 70.6°. **Second-scene test E6–E9 prepared, not run** (§12.4–12.7). It uses the `--setup-preview` mode, which passed 38 offline checks but is **untested with a physical camera or real OpenCV window**. The Camera B correction decision rule is pre-specified. CRATER coverage check prepared, not run. Headset comfort not tested. |
| Task 03 Stage F: Image-quality assessment | Pending |
| Task 03 Stage G: Camera-validation report | Pending (this file is an interim checkpoint, not the Stage G report) |
| Task 04A: Open-source streaming and architecture audit | **Completed 5 Nov (research only); awaiting review** (§13) |
| Task 04A addendum: COROL integration audit | **Completed 5 Nov (source inspection only); reviewed.** Architecture approved as provisional; robot control on hold (§13.1–13.2) |
| Task 04B: Offline streaming proof of concept | **Complete (closed 5 Nov at the G1 gate).** G1.1–G1.7 PASS on both streams in the uninterrupted rerun. S7b recorded as FAIL (v2 proposed for future tests); F3b NOT_TESTED; ~300 ms delays unresolved (§13.3–13.10) |
| Task 05: Unity Windows reception | **Compatibility milestone PASS (5 Nov, offline):** project `unity/Phase2Client` created; FFmpeg.AutoGen 9.0.1.1 with the BtbN FFmpeg 9.0 LGPL build verified in the Editor and a standalone player (§13.11). M1 offline verified; T3 PASS; **T4 run 5 Nov: formal M1 FAIL on M1.4–M1.6 (§13.15), the recorded result**; 6 Nov: scoring corrections approved and implemented, **supplementary post-hoc re-score under M1 criteria v2: PASS 10/10** (§13.16). **M1 CONDITIONALLY VALIDATED (6 Nov, §13.17)** ([plan](../docs/plans/Phase2_Task05_Unity_Windows_Reception_Plan.md)) |
| Task 06: real Camera A to Unity preview | Offline readiness complete; Stage 0 PASS (§13.17). **Stage 1 PASS (6 Nov 12:28): on-device H.264 of both rectified eyes verified**, 0 gaps, L/R skew ≤ 0.034 ms, calibration and bootloader unchanged (§13.18). **Stage 2 live preview 6 Nov 12:56: integrity PASS S1–S11**; capture → Unity median 90.7 ms; 6 freezes of about 1 s from right-eye loopback transport stalls (§13.19) |
| Task 04: Standalone stereo camera gateway | Not started; proposed direction in §13 |
| Unity Editor installation | **6000.3.28f1 (6.3 LTS) installed;** URP test project and Play Mode work. Android Build Support and Quest deployment not verified (§13.10) |

---

## Handover status (end of 4 November 2026)

### Tested and not tested

| Item | Status |
|---|---|
| Stages B, C (initial), D | Complete on hardware (§6.9, §7.8, §9) |
| Stage E E1–E5 | Complete on hardware and analysed (§11); provisional configuration approved (§12.1) |
| Stage E E6–E9 | **Prepared, not run** (§12.4, §12.7) |
| `rectify_stereo.py --setup-preview` | **38 offline checks passed; not yet tested with a physical camera or a real OpenCV window** (§12.7). Window focus, key handling and behaviour behind other windows on this laptop are unverified. |
| `analyse_epipolar.py`, `coverage_check.py` | Offline checks passed (§12.3); not yet run on second-scene data |
| CRATER coverage check | Prepared, not run (§12.5); markers ready to print (`results/coverage_markers_20261104_173011_140mm`) |
| Stage F (image quality), Stage G (report), Task 04 (gateway) | Not started. The Task 04A audit (5 Nov) proposes the direction in §13; implementation awaits review |

### Outstanding issues

1. **Camera B vertical alignment.** A consistent offset of −0.64 to −0.96 px (about −5 arcmin), a relative roll of about 0.06°, and local upper-left errors up to about 3.6 px. The lower third and very near objects are unverified. E6/E7 test whether this is scene-independent; any software correction follows the pre-specified rule (§12.4) and is **never applied to the live stream or the camera** without approval.
2. **CRATER coverage.** Whether Camera B's 97.1° × 70.6° covers the construction area from the planned tripod position is untested (§12.5).
3. **Quest 3 viewing comfort.** Untested for both cameras. Also open: the 7.5 cm baseline (about 1.2× hyperstereo) and matching the 2D monitor's angular size (§11.9 items 5–6).
4. **Intermittent frame-delivery stalls.**
   - On the local link, stalls of 0.1–0.7 s occur about 2.7 times per minute. Frames are lost only when the backlog exceeds about 6–7 frames (13 of 8,413 in Stage D).
   - The root cause is unknown; TCP retransmission timeouts are a hypothesis only. The decisive test is a packet capture, which needs admin/IT approval (§9.6–9.8).
   - This does not block Stage E, but it matters for the streaming gateway and for timing in the supervision interface (§9.7).
5. Smaller open items:
   - the Stage B address-resolution failures (no confirmed root cause; `--expect` guards against them);
   - the PoE switch model and port assignment are not recorded;
   - the field of view of the 1280 × 720 sensor mode is unchecked;
   - the IT request about Wi-Fi/Ethernet (Group Policy `fMinimizeConnections = 3`);
   - Unity 6000.3.4f1 is not installed (superseded 5 Nov: 6000.3.28f1 is installed, §13.10);
   - several saved images contain an identifiable person (data handling).

### Safeguards confirmed (offline check, end of 4 Nov)

- **Auto-calibration:** all **16** pipelines started so far recorded `AutoCalibrationMode.OFF`.
  - `capture_stereo.py` and `rectify_stereo.py` each create exactly one pipeline, set `AutoCalibrationMode.OFF`, and refuse to start unless the getter confirms it.
  - `discover_cameras.py` and `calibration_check.py` create no pipeline.
- **Calibration unchanged in every run where it was verified:** 14 runs checked in-session, after the read-only reconnection, and against both 3 November baselines; user = factory throughout. Both standalone checks (15:37 and 15:40) passed.
  - The two exceptions are the 15:22/15:23 Stage C runs, which stay recorded as **FAIL** because of the old verification defect (§7.5). Their start-of-run calibration matched the baseline, and the 15:37 standalone check confirmed Camera A afterwards.
- **IR:** IR off is acknowledged before and after every pipeline start.
- **Identity and shutdown:** verified device-ID selection and clean shutdown, with a read-only post-run reconnection.
- **Nothing written to the cameras:** no firmware, bootloader, IP, MAC, EEPROM or calibration has been written. No robot software has been run, and the original Side Quest repositories are untouched.
- **Earlier results preserved:** all **19** run folders are unmodified since their runs; offline tests write only to the scratchpad.
- **Current code passes all three offline suites:** `capture_stereo`, `rectify_stereo` (including the setup preview) and `analyse_epipolar` / `coverage_check`.

---

## NEXT SESSION: START HERE

> **Software track (13 Nov 2026), restart here (§13.35, §13.34, §13.33):**
> - **Development baseline committed:** Unity `d7371d6` (§13.35); backup `backups/20261113_video_baseline_checkpoint/`.
> - **O1 ETW camera capture (§13.40):** ran cleanly (0 lost) but **no hold occurred**: a clean-streaming baseline and **INCONCLUSIVE for O1**. Not evidence that O1 is resolved; not to be repeated automatically. Raw ETL retained and hashed; CSV deleted after validation. Deviation: the O2 reconnect start was partly traced (the runner does not wait for the trace to stop).
> - **O1 ETW feasibility (§13.39):** verified connection identity, seq/ack/window, SYN retransmission, ms alignment. Data retransmission and zero-window are still unverified on real traffic.
> - **16 Nov (§13.41):** commissioning view completed and verified offline (EditMode 211/211; scripted player 23/23; `run_stage2.ps1 -Player Commissioning` plan-only verified); uncommitted; not run live. COROL adapter proposed, awaiting approval.
> - **17 Nov (§13.42):** commissioning view **live-checked with Camera A** (two runs, analyser S1–S11 PASS both) and **committed `6d65e06`** (local, not pushed). Click-to-zoom is not yet live-tested. COROL: next, identify the researcher's existing launch procedure; no routine host or handover yet.
> - **17 Nov (§13.43):** **Unity → COROL twin, simulation-only integration built and verified** (`corol_sim/`, e2e 8/8, EditMode 223/223); visual walkthrough passed 15:31 *(user-reported)*; Unity committed `04e6fd0`; corol_sim backed up in `backups/20261117_corol_sim_baseline/`. CRATER visit postponed; next is one experiment-like S4 trial against the twin (analysis first).
> - **17 Nov evening (§13.45):** Phase 2 scene GLB aligned in the twin (transform recorded); one-placement S4 rehearsal with a scripted RegoLight brick on the twin, e2e 16/16, EditMode 232/232; ACCEPTED visually 18 Nov, committed `37e93f0`. Launch: `corol_sim\start_corol_sim.ps1 -Rehearsal`.
> - **18 Nov (§13.46):** viewing rehearsal (site view = Camera A filming a display; wrist view = rendered virtual camera; require_live) built and verified OFFLINE (viewing_e2e 15/15, EditMode 245/245); UNCOMMITTED. Next: position Camera A, then `start_corol_sim.ps1 -Viewing` + `run_stage2.ps1 -Player S4CorolViewing -ExtendedTest` (README walkthrough). Launch: `corol_sim\start_corol_sim.ps1`. COROL unchanged. Physical control still needs the handover decision, stop semantics and on-site commissioning.
> - **Next priority (researcher, 13 Nov):** Roseworthy commissioning on Wednesday: repeatable live-camera viewing launch, inspection controls and evidence recording, and preparation for COROL (status check and one named routine trigger; plan before implementation).
> - **Commits:** S4.1 `6c7e33c`; live-source `ca5c803`; live smoke milestone `807ef39` (accepted as development integration only).
> - **Backups:** `backups/20261113_live_smoke_checkpoint/` and `backups/20261112_live_camera_restart/`.
> - **Uncommitted, for review:** the extended-test mode for the full interactive demo, verified offline: `camera_gateway_a.py --extended-test` (hard 600 s), `run_stage2.ps1 -Player S4Demo -ExtendedTest`, `analyse_stage2.py --player s4demo`, `tools/summarise_live_walkthrough.py`.
> - **Live walkthrough (§13.28, §13.29):** accepted as a functional integration milestone. Streaming continuity is NOT accepted.
> - **O1 diagnosis (§13.30):** a near-constant ≈ 310 ms per-connection hold on the gateway → MediaMTX loopback, which backs up into the write; the age guard and resync then cause 0.5–1.05 s freezes. Retransmission timeout is the best-fit hypothesis. The next test is a read-only TCP counter sampler (approval pending).
> - **TCP diagnostic (§13.31):** 7/7 hold releases coincide with a single system-wide TCP retransmission. The background chance of that is about 1 % per hold; supporting evidence, not proof.
> - **Unity fixes (§13.32, uncommitted, offline-verified):** real-pair readiness; stale-image status and dimming; observation gate and continuity records. EditMode 194/194; players rebuilt (S4, S3, S2). Recovery-policy decisions R1–R6 are open; a live check needs approval.
> - **Live verification (§13.33):**
>   - V1, V3, V4, V5 and V6 pass; V2 passes with one logged exhausted-recording exception on Camera B.
>   - Brief 17–65 ms "Image not current" excursions about 3.4 per minute on Camera A.
>   - The exhaustion drain shows as an interruption for 3 s.
>   - S6 fails from an existing S4.1 inactive-location double count.
>   - Deferral and receiver failure untested live.
> - **Corrections (§13.34, uncommitted):**
>   - Inactive locations counted once per trial instance; the §13.33 integrity failure is fully explained and corrected by reanalysis.
>   - Recorded-source exhaustion is reported at EOF plus final frames, with no interruption sequence.
>   - Stale dim verified on rendered pixels (slope 0.4006 against 0.400).
>   - EditMode 198/198.
> - **O2:** unresolved; tied to the scoped unicast reconnect.
> - **Hardware:** **only Camera A** on the PoE switch. The dual-camera MAC anomaly is unresolved, and the guard is not bypassed.
> - **Known:** each trial start shows Camera A about 1.5 s before its first image (planned receiver restart).
> - **Still open:** the 12 Nov 1.1 s freeze, reconnection, inter-site connectivity, long-duration reliability, and D1–D10.
> - **After any reboot:** recheck C09. S4.2 has not started.

**Goal: one Camera B second-scene run (E6) with the setup preview, then check it before running E7–E9.**

**1. On Wi-Fi, before connecting anything**
```powershell
cd C:\Users\a1920234\Documents\Phase2_Interface\camera_validation
.venv\Scripts\python.exe env_check.py
```
Confirm DepthAI 3.11.0, OpenCV 4.14.0 and NumPy 2.4.6. Re-read §12.4 (scene) and §12.7 (preview).

**2. Set up the E6 scene (Camera B, mixed depth, full field)**
- Tripod about 1.2–1.5 m high, tilted so the **lower third sees a textured floor or table** at 0.8–1.5 m.
- Textured sheets near **all four corners**.
- Objects at about 1 m, 2–3 m and 4–6 m.
- Ordinary lighting, **no people in view**.
- Note the distances and the tripod height and tilt.

**3. On Ethernet only (Camera B attached), run E6 alone**
```powershell
cd C:\Users\a1920234\Documents\Phase2_Interface\camera_validation
$B = "--expect","169.254.1.223=194430108183F12E00","--baseline-user","results\calibration_user_194430108183F12E00_20261103_183335.json","--baseline-factory","results\calibration_factory_194430108183F12E00_20261103_183335.json"
$S = "--groups","60","--warmup-groups","30","--save-groups","10","--setup-preview"
.venv\Scripts\python.exe rectify_stereo.py @B @S --label E6_B_s2_mixed
```

- **In the preview window** (click it first so it has keyboard focus; it may open behind VS Code):
  1. Adjust the targets until every grid cell shows clearly non-zero texture counts (roughly 30 or more), especially the bottom row and the corners.
  2. Step out of view.
  3. Press **Space** and keep the scene still for about 12 s until `RESULT:` appears.
- **To abort,** press **Q or Esc**: the result is `CANCELLED`, nothing is captured, and the run can be repeated.
- **If the window misbehaves** (frozen, keys ignored), use Ctrl+C, which shuts down cleanly. Note the behaviour; the fallback is the same command without `--setup-preview`.

**4. Check E6 before continuing (on Wi-Fi; offline)**
- The console shows **`RESULT: PASS`**, `Calibration: in-session equal True | post-run (read_ok) equal True, baselines [... True, ... True] | unchanged: True`, `Device closed: True`, and no new crash dump.
- Run the coverage and consistency check against scene 1:

  ```powershell
  .venv\Scripts\python.exe analyse_epipolar.py --run E2_B_default:scene1 --run E6_B_s2_mixed:scene2 --fit-on E2_B_default --evaluate-on E6_B_s2_mixed
  ```

- **Continue to E7–E9 only if:**
  - E6 passed with calibration unchanged;
  - the preview behaved correctly;
  - coverage is adequate: **at least 20 of 25 cells verified, including at least 3 cells in the lower third** (rows 4–5).

  If coverage is short, re-arrange the scene and repeat E6 under a new label (e.g. `E6b_B_s2_mixed`). Every attempt is kept.

**5. Then the remaining runs** (Ethernet; at least 30 s between runs; same `$S`)
```powershell
$A = "--expect","169.254.1.222=19443010B14C872F00","--baseline-user","results\calibration_user_19443010B14C872F00_20261103_182445.json","--baseline-factory","results\calibration_factory_19443010B14C872F00_20261103_182445.json"
.venv\Scripts\python.exe rectify_stereo.py @B @S --label E7_B_s2_near
.venv\Scripts\python.exe rectify_stereo.py @A @S --preview-crop 39,6,1276,775 --label E8_A_s2_mixed
.venv\Scripts\python.exe rectify_stereo.py @A @S --preview-crop 39,6,1276,775 --label E9_A_s2_near
```

**6. Full offline analysis afterwards** (§12.6), then apply the Camera B decision rule (§12.4):
```powershell
.venv\Scripts\python.exe analyse_epipolar.py --run E2_B_default:scene1 --run E6_B_s2_mixed:scene2 --run E7_B_s2_near:scene3 --run E1_A_default:scene1 --run E8_A_s2_mixed:scene2 --run E9_A_s2_near:scene3 --crop 39,6,1276,775 --fit-on E2_B_default --evaluate-on E6_B_s2_mixed,E7_B_s2_near
.venv\Scripts\python.exe analyse_epipolar.py --run E6_B_s2_mixed:scene2 --run E2_B_default:scene1 --run E7_B_s2_near:scene3 --fit-on E6_B_s2_mixed --evaluate-on E2_B_default,E7_B_s2_near
```

**Later, each needing separate approval:**
- the CRATER coverage check (§12.5);
- the Quest 3 comfort check;
- Stage F (image quality, using the approved configuration);
- the packet-capture decision for the stalls (§9.8);
- Task 04B: review the localhost MediaMTX config, scripts and offline test results (§13.2). If approved, launch MediaMTX, run the smoke test, then the G1 run ([streaming_poc/README.md](../streaming_poc/README.md)). No cameras are needed.
- Review and edit the draft AIML questions before sending ([docs/coordination/CRATER_AIML_Questions_DRAFT.md](../docs/coordination/CRATER_AIML_Questions_DRAFT.md)). No robot work until they are answered.

**Do not:**
- start any DepthAI pipeline without `AutoCalibrationMode.OFF` confirmed (it may flash user calibration; §7.1);
- use `--ip` mode with both cameras attached (use `--expect`; §6.6–6.8);
- change camera IP addresses or MACs, update bootloaders (including to 0.0.29), or overwrite calibration;
- enable the IR projector or flood light;
- apply a Camera B correction to a live stream without approval;
- start robot-control software or move the robot;
- modify the original Side Quest repositories;
- change Windows network or university settings.
