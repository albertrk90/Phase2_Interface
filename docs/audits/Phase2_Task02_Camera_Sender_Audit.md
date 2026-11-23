Written for: you and the Phase 2 developers who will build the standalone sender and the Unity clients.

# Task 02 audit: original Side Quest camera sender

I only read files. Nothing was modified, installed, started or connected. Where a finding depends on DepthAI or Unity behaviour I could not check from the code, it is marked **[verify]**.

## 1. Summary

- **The sender has two different pipelines, and the code does not record which one was used.** The DepthAI v2 path does what the design docs describe: JPEG encoding on the camera and an on-camera Sync node. The v3 path does neither. It sends raw frames, pairs left and right with no check that they belong together, and encodes JPEGs on the Pi's CPU. No DepthAI version is pinned anywhere in the repo.
- **The wire format matches `TogglableReceiver` byte for byte.** The problems are in behaviour:
  - Only one client can connect at a time.
  - Pairs carry no frame ID or timestamp.
  - A lost camera fails silently.
  - Neither side reconnects automatically.
  - Switching cameras in Unity can mix frames from both cameras.
- **Neither path produces rectified images.** Both send raw left/right mono images.
- **The sender cannot currently run without the robot hardware.** It is only ever started from `task_controller.py`. That script connects to the RS485 gripper at import time and stops if it fails. It also opens the robot command server, which arms the robot when Unity connects.
- **Isolating it is cheap.** `camera_streamer.py` only imports `robot_config` (no side effects) and takes the perception engine as an optional argument. A separate launcher is enough for a baseline; `camera_streamer.py` itself needs no change.

## 2. Verified sender architecture

**Call chain in the original system**

```
run_controller.sh:85 → task_controller.py (module-level script)
  :17-18   import DobotDriver, DHGripperPGE
  :40      os.environ["DEPTHAI_WATCHDOG_TIMEOUT"]="5000"
  :42-47   ports 8085/8086/8088; camera IDs from robot_config
  :59-66   construct DobotDriver (lazy), DHGripperPGE
  :1028    _initialize_gripper_on_startup()  ← raises if gripper absent
  :1049-57 import camera_streamer
  :1059-71 camera_server_wrapper(mxid, port, label)
             → vision_controller.camera_stream_perception_binding(label)
             → camera_streamer.start_camera_server(...)
  :2982    command-server thread (8088; arms robot on VR connect, :2635/:2651)
  :2986    thread "camera-inspector"  (INSPECTOR_CAMERA_IDS → 8085)
  :2987    time.sleep(10)
  :2988    thread "camera-site-manager" (MANAGER_CAMERA_IDS → 8086)
  :3002-25 Ctrl+C → STOP_EVENT.set() → join 3 s → os._exit(0)

```

**v2 pipeline** (camera_streamer.py:106-144, 218-250)

```
MonoCamera CAM_B 720P@20 → VideoEncoder MJPEG q40 ─┐
                                                   ├→ Sync(50 ms) → XLinkOut "out"
MonoCamera CAM_C 720P@20 → VideoEncoder MJPEG q40 ─┘
[opt] MonoCamera CAM_B.out → XLinkOut "rawL" (perception only)
Host: getOutputQueue("out", maxSize=4, blocking=False) → group["left"/"right"].getData()

```

**v3 pipeline** (camera_streamer.py:253-300)

```
Camera.build(CAM_B, sensorFps=20).requestOutput((1280,720), GRAY8) → createOutputQueue()
Camera.build(CAM_C, sensorFps=20).requestOutput((1280,720), GRAY8) → createOutputQueue()
Host: left_q.get(); right_q.get()   (no pairing check)
      → cv2 GRAY→BGR → cv2.imencode JPEG q40 (Pi CPU)

```

**Function reference**

| Function                                         | Lines   | Role                                                                       |
| ------------------------------------------------ | ------- | -------------------------------------------------------------------------- |
| `_create_node`                                   | 25-40   | Creates nodes using whichever API the installed version has                |
| `_supports_v2_xlink` / `_supports_v3_camera_api` | 43-53   | Chooses the path: v2 if `XLinkOut` exists, else v3 if `node.Camera` exists |
| `_device_identifiers` / `_resolve_device_info`   | 56-103  | Matches a configured MXID or IP against discovered devices                 |
| `_build_v2_pipeline`                             | 106-144 | On-camera encoding and sync                                                |
| `_to_bgr` / `_to_jpeg_bytes`                     | 152-167 | Host-side encoding (v3 only)                                               |
| `_send_stereo_payload`                           | 170-172 | Wire framing                                                               |
| `_configure_perception`                          | 175-188 | Reads calibration and starts the ArUco worker on the `rawL` queue          |
| `_serve_socket_loop`                             | 191-215 | Accept/send loop, one client at a time                                     |
| `_run_v2_server` / `_run_v3_server`              | 218-300 | Device lifetime and server socket                                          |
| `start_camera_server`                            | 303-332 | Entry point; catches every exception, prints it and returns                |

## 3. Findings by focus area

**1. Acquisition and synchronisation**

- **v2:** sync is done on the camera. The 50 ms Sync threshold is a full frame period at 20 fps (:131). If one eye drops a frame, it can pair L(n) with R(n±1). The OAK-D Pro mono sensors should be hardware-synchronised **[verify]**, so the threshold should be about 5–10 ms.
- **v3:** there is no Sync node. The two queues are read one after the other (:290-291). If one queue drops a frame and the other does not, every later pair is out by one frame and nothing detects it.

**2. v2 vs v3 differences**

|                              | v2                                          | v3                                                                                          |
| ---------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------- |
| JPEG encoding                | Hardware, on the camera                     | `cv2.imencode` on the Pi, 3-channel                                                         |
| L/R pairing                  | Sync node, by timestamp                     | None                                                                                        |
| Queue between camera and Pi  | Holds 4 frames, drops the oldest            | Default `createOutputQueue()` size and blocking mode **[verify]**                           |
| Camera→Pi traffic per camera | Compressed, \~10–20 Mbit/s (estimate)       | Raw GRAY8: 2×1280×720×20 B/s ≈ **295 Mbit/s**                                               |
| Image area                   | `THE_720_P` sensor mode                     | `requestOutput` resize/crop from the 1280×800 sensor; field of view may differ **[verify]** |
| Version requirement          | Sync node needs depthai ≥ 2.24 **[verify]** | Any v3                                                                                      |

XR_tech_brief.md section 4 ("near 0% Pi CPU", Sync node) describes the v2 path only. The config comment "allow current PoE device ids" (robot_config.py:61) and the deprecation-warning filter suggest a later move to v3. This is not confirmed. requirements.txt lists only pymodbus and pyserial, and the Pi's environment (`~/regolith-robotics-env`) is not in the repo.

**3. Rectified or unrectified:** both paths send unrectified images.

- v2 uses `MonoCamera.out` with no StereoDepth node, so images are raw and still lens-distorted.
- v3 `requestOutput` does no stereo rectification. Whether it applies lens undistortion by default depends on the version **[verify]**.
- On the Quest, the eyes will therefore receive images with vertical disparity and lens distortion. The OAK baseline is about 75 mm, against a typical IPD of about 63 mm.

**4. Camera identification:**

- Each thread calls `dai.Device.getAllAvailableDevices()` and matches any configured candidate against `getMxId()`, `mxid`, `mxId` or `name` (`name` is the IP for PoE devices).
- Candidates come from robot_config.py:62-69:
  - INSPECTOR: `19443010B14C872F00` / `169.254.1.222`
  - SITE_MANAGER: `194430108183F12E00` / `169.254.1.223`
- v3's `getDeviceId()` is not checked, so on v3 a match may rely on the IP fallback only **[verify]**.
- Cameras are opened 10 s apart (`task_controller.py:2987`) to avoid PoE boot contention (PHASE1_CAMERA_PROBE.md:11).
- If a camera is not found, the thread prints the error and exits. Nothing retries, and the port is never bound.

**5. Encoding and bandwidth:**

- 1280×720, 20 fps, JPEG quality 40 (constants at :14-17). Quality 40 is low and the artefacts may affect stereo fusion; it is worth treating as an experimental variable.
- Pi→client traffic is roughly 35–60 KB per eye-frame, about 11–19 Mbit/s per camera per client. This is an estimate and must be measured.
- On v3, both cameras plus the optional perception stream send about 740 Mbit/s of raw frames over the Pi's 1 GbE link, whether or not anyone is watching.

**6. Pair association:**

- During capture and encoding, only v2 associates the two eyes (by Sync-node timestamp).
- On the wire, the association is only that R follows L. Timestamps and sequence numbers are available from DepthAI but thrown away (`getData()` only).
- In Unity, `Update()` shows whatever the latest L and R are once both ready flags are set (TogglableReceiver.cs:66). If L1, R1 and L2 all arrive between two `Update()` calls, it displays L2 with R1.

**7. Multiple clients:** not supported.

- `listen(1)` and a serial accept loop serve one client per port.
- A second client completes the TCP handshake (it sits in the backlog) but receives nothing.
- The receiver has no read timeout, so that client shows a frozen frame and raises no error.

**8. Failure handling**

| Event                       | Behaviour                                                                                                                                                                                                                                                          |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Client disconnects          | `sendall` raises → caught silently (:211-213) → back to accept. Recovers.                                                                                                                                                                                          |
| Slow client                 | A 1 s send timeout drops the client. No frames are skipped first.                                                                                                                                                                                                  |
| Camera disconnects          | The read from the camera raises an XLink error, which the same `except Exception: pass` swallows. Back to accept; every new client is then dropped immediately. The device is never reopened and nothing is logged. **Camera loss looks the same as client loss.** |
| Camera stalls with no error | The camera read blocks forever and `stop_event` is never checked.                                                                                                                                                                                                  |
| No client connected         | Frames are not read. On connect, the first frames are stale (v2: up to 4 ≈ 200 ms; v3: up to the queue default).                                                                                                                                                   |
| Process shutdown            | Relies on `STOP_EVENT` plus `os._exit(0)` (task_controller.py:3025). The camera server sockets are not in the controller's list of sockets to close (:201-223). The device is released by the 5 s watchdog env var, which a standalone launcher must also set.     |

**9. Dependencies**

| Module                                                                                 | How it is used                                                                                     | Needed standalone?             |
| -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------ |
| `robot_config`                                                                         | Only `DEBUG_ENABLED` in `_cam_info`. No side effects on import. Camera IDs are read by the caller. | No: replace with sender config |
| `task_controller`                                                                      | Caller: ports, IDs, `STOP_EVENT`, watchdog env, thread start, shutdown                             | No: replace with launcher      |
| `vision_controller` → `perception_engine` → `aruco_tracker`, `logger`, `vision_bridge` | Only through `perc_engine` when `enable_rawL` is true                                              | No: pass `enable_rawL=False`   |
| `depthai`, `cv2`, `numpy`                                                              | Required                                                                                           | Yes. **Not pinned anywhere.**  |
| `typing.Iterable`                                                                      | Imported but unused                                                                                | —                              |

**10. Isolation:**

- `camera_streamer.py` has no motion imports. No other module imports it (depth_stream_probe.py:47 imports helpers from `phase2_calibration_capture` instead).
- The only obstacle is the launcher. `task_controller` fails without the gripper (:1028, :78-79), and it combines video with the 8088 arming channel.
- `DobotDriver()` does not connect when constructed (dobot_driver.py:56-67).

## 4. Compatibility with `TogglableReceiver`

| Element                                 | Sender (:170-172)                      | Receiver (:84-100)                                     | Match                                                     |
| --------------------------------------- | -------------------------------------- | ------------------------------------------------------ | --------------------------------------------------------- |
| Tag                                     | 1 byte `'L'` (0x4C) / `'R'` (0x52)     | `ReadBytes(1)`; 76 / 82, other values ignored          | ✓                                                         |
| Length                                  | `struct.pack(">I")`, uint32 big-endian | 4 bytes, reversed on little-endian, `ToInt32` (signed) | ✓ below 2 GiB                                             |
| Payload                                 | Complete JPEG                          | `ReadBytes(size)` → `LoadImage` on the main thread     | ✓, but v2 mono MJPEG decoding in `LoadImage` **[verify]** |
| Order                                   | Always L then R                        | Order-independent                                      | ✓                                                         |
| Handshake, version, frame ID, timestamp | None                                   | None                                                   | ✓ (both missing)                                          |
| Transport                               | TCP server `0.0.0.0:8085/8086`         | `TcpClient("169.254.1.10", 8085)`                      | ✓                                                         |

**Verdict:** the framing is compatible. Receiver-side defects:

1. **Switching cameras can mix frames from both cameras.** `SwitchCameraSource` calls `Thread.Abort()` (:59), which does not interrupt a thread blocked in a socket read and is not supported under IL2CPP, which Quest standalone builds use **[verify]**. `isRunning` is shared and set back to true straight away, so the old thread keeps writing old-camera frames into the same buffers. The old socket is never closed, and the ready flags are not cleared.
2. It never reconnects. One failure ends `ReceiveLoop`.
3. There is no read timeout and no signal-loss indicator. A stalled stream looks like a frozen live image.
4. It does not check for short reads. A truncated payload is still marked ready, and a desynchronised length field can trigger a huge allocation.
5. It allocates a new buffer for every frame and decodes two 720p JPEGs per frame on the main thread. This causes garbage-collection pauses and frame-time spikes, which are worse on standalone Quest than over Link.
6. It needs a material shader with `_LeftTex` and `_RightTex`. That shader is not in this repo.

## 5. Risks and missing dependencies (ranked)

1. **Running video through `task_controller` is unsafe**, because the same process arms the robot on 8088. A standalone sender is required, not optional.
2. **The DepthAI version is unknown**, and it decides whether sync and on-camera encoding happen at all.
3. **The v3 path has no stereo pairing**, which makes it unsuitable for Phase 2 as written.
4. **Camera loss fails silently and permanently** until the process restarts.
5. **Only one client per camera**, so desktop and Quest cannot watch the same camera at once.
6. **Images are unrectified**, which affects stereo comfort and validity in the experiment.
7. **No frame IDs or timestamps**, so latency and synchronisation cannot be measured or logged.
8. **Unity camera switching is unreliable** (see section 4, item 1).
9. **Missing or unrecorded dependencies:** no depthai/opencv/numpy pins, the Pi venv is undocumented, and the shader is absent.
10. **Smaller issues:** `TCP_NODELAY` is not set, and with `DEBUG_ENABLED=False` all logging except fatal errors is suppressed.

**Items to verify on hardware later**

- depthai version and which path runs.
- Sync node availability.
- Whether the mono pair is hardware-synchronised, with the measured L–R timestamp difference.
- v3 queue defaults and undistortion default.
- Whether `LoadImage` decodes the v2 mono MJPEG output.
- `Thread.Abort` behaviour in the target Unity build.
- Actual JPEG sizes and bitrate.
- That the watchdog env var takes effect when set after `import depthai`.
- That device discovery works across the Phase 2 network (link-local 169.254.x).

## 6. Minimum changes for a standalone sender

1. **New launcher** (for example `stereo_sender.py`). It sets `DEPTHAI_WATCHDOG_TIMEOUT`, creates a `threading.Event`, and starts two threads calling `start_camera_server(ids, port, label, enable_rawL=False, stop_event=ev, perc_engine=None)` with the 10 s stagger. Ctrl+C sets the event. It imports nothing from motion or perception.
2. **Replace `import robot_config`** with a small sender config (CLI arguments or env) for IDs, ports, debug flag and logging.
3. **Pin dependencies** in a separate sender requirements file: the verified depthai version, `opencv-python-headless`, `numpy`.
4. **Log instead of swallowing** in `_serve_socket_loop`, and treat a camera exception differently from a client disconnect.

Changes 1–3 reproduce the original behaviour with no robot dependency. Change 4 is the smallest change that makes failures visible.

## 7. Staged plan with acceptance tests

| Stage                                       | Scope                                                                                                                                                                                                                                                                                                                  | Acceptance tests                                                                                                                                                                                                                                                                                  |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **0. Verify environment**                   | Record depthai version and path; list devices; check the Sync node and queue defaults. Read-only probes, run once you approve hardware access.                                                                                                                                                                         | Version recorded; both cameras resolved by ID; chosen path recorded; L–R device timestamp difference measured over 1,000 frames.                                                                                                                                                                  |
| **1. Standalone baseline**                  | Changes 1–3 from section 6; wire format unchanged.                                                                                                                                                                                                                                                                     | Starts with gripper and Dobot unplugged; after startup no motion module or `pymodbus`/`serial` is loaded; nothing listens except 8085/8086; no traffic to 192.168.5.x; existing `TogglableReceiver` shows both ports; Ctrl+C exits in under 3 s and cameras are rediscoverable within 10 s.       |
| **2. Sender robustness (same wire format)** | Use the Sync node in both paths (or match by sequence number); threshold ≤ 10 ms; hold only the latest frame and drop stale ones; one acquisition thread per camera and one sender thread per client, with drop-not-block; reopen the camera after a failure; `TCP_NODELAY`.                                           | 10 min run: 100 % of pairs within threshold; at most one stale frame on connect; two clients on one port each receive ≥ 95 % of pairs; unplugging a camera is logged within 2 s, and the camera recovers within 15 s of replug with no restart; a slow client never reduces the acquisition rate. |
| **3. Protocol v2**                          | One message per stereo pair, with: magic, version, message type, camera ID, flags (rectified, sync OK), u64 frame sequence, L/R capture timestamps (host-synced), send timestamp, width/height, L/R lengths, then both JPEGs. A heartbeat/status message reports signal loss. Served on new ports so v1 keeps working. | Sequence numbers increase monotonically, with gaps counted; heartbeats arrive at 1 Hz even with no frames; status changes to CAMERA_LOST within 2 s; a decoder test passes on recorded captures.                                                                                                  |
| **4. Unity clients**                        | Shared receiver: cancellation through socket close (no `Abort`), read timeouts, reconnect with backoff, pairing by sequence number, latest-only display, signal-loss overlay. Desktop client shows one eye; Quest client shows stereo. Switching: keep both camera connections open and switch locally (recommended).  | Switching cameras 100 times shows no mixed-camera pair; restarting the sender recovers within 5 s; sender killed → overlay within 2 s; Quest build (IL2CPP) passes the same tests.                                                                                                                |
| **5. Rectification**                        | StereoDepth rectified outputs fed to the encoders, behind a flag.                                                                                                                                                                                                                                                      | Checkerboard vertical disparity < 1 px after rectification; the flag is reported in the header.                                                                                                                                                                                                   |
| **6. Soak and latency**                     | 60 min soak with both clients; glass-to-glass latency using an on-screen clock in view.                                                                                                                                                                                                                                | No memory growth; latency and drop rate logged per camera; results recorded as baseline experiment metadata.                                                                                                                                                                                      |

Robot commands stay out of scope for all of these stages. Every stage repeats the Stage 1 isolation test.

I can also put this report on a shareable page or in a doc.