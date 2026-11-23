# Side Quest Unity Project — Read-Only Technical Audit for Phase 2

**Repository:** `SideQuestXR_Unity` (UVCS workspace at `C:\Users\a1920234\Documents\SideQuest_Recovery`)
**Unity:** 6000.3.4f1 · **Audit date:** 2026-11-03 · **Method:** static inspection of source, YAML scenes and prefabs, materials, shader graphs, project settings, and the checked-in Windows build. Nothing in the project was modified. Unity was not opened and no network or robot connections were made.

**Evidence labels**
- **[V] Verified:** read directly from repository files (path and line or object given).
- **[I] Inferred:** a reasonable reading of the code or configuration.
- **[U] Unverified:** needs Unity, the Pi or robot software, or the hardware to confirm.

Paths are relative to the project root. Scene object paths are given as GameObject hierarchy paths in `Assets/Scene/SideQuest_v2.unity`.

---

## 1. Executive summary

1. **Live stereo video is implemented on the Unity side only.** [V] Unity receives two JPEG streams, one per eye, over a custom raw-TCP protocol, decodes them on the main thread, and shows them on one flat world-space quad. A shader picks the left or right texture per eye using Shader Graph's *Eye Index* node. The **sender is not in this repository.** [V] It ran on a device at `169.254.1.10` (presumably a Raspberry Pi, from the `piIp` field names), on ports 8085 and 8086. No Python, Pi, DepthAI or Dobot code exists here. [V]
2. **There is no WebRTC, RTSP, WebSocket, H.264, native video plug-in or rectification.** [V] The active path is a hand-rolled length-prefixed JPEG framing over `System.Net.Sockets.TcpClient`. An archived V1 used HTTP MJPEG with a side-by-side frame.
3. **Camera switching exists.** [V] Two buttons, "TopView" and "SideView", reconnect the same receiver to a different TCP port (8086 or 8085). Each port is a separate stereo source. Nothing reconnects automatically after a drop. [V]
4. **Robot integration is indirect.** [V] Unity never talks to the Dobot. It sends newline-delimited ASCII commands (START, DROP, FIX, NUDGE, and so on) over TCP to a "command hub" at `169.254.1.10:8088` and gets ACK/NACK and game events back. ROS-TCP-Connector is installed but no project code uses it.
5. **Much of the current UI is unsuitable for Phase 2 as it stands.** [V] It contains explicit placement-correctness cues: a GREEN/YELLOW/RED zone sphere on the video screen and zone-specific drop sounds. It also contains gamification (combo, boost, "GAME OVER", music ducking) and direct-manipulation nudge controls.
6. **Reusable foundations:** [V/I] URP + OpenXR Quest 3 configuration; the XRI 3.3 rig and world-space UI; the per-eye stereo material and shader; the receiver threading pattern; the ACK/NACK and decision-token state-machine pattern; the lunar terrain and Earth environment assets.
7. **Recommendation, in brief:** build the 2D condition as a **Unity desktop build from the same project**, not a browser. The same receiver, decoder and material then serve both conditions. The 2D view is simply the left eye (Eye Index = 0 outside stereo rendering), which keeps image properties identical so that only stereopsis differs. For Milestone 1, write a new CRATER-side DepthAI sender that speaks the existing L/R JPEG framing, so the Unity side needs only small changes. Re-evaluate the transport (H.264 or WebRTC) once latency and bandwidth over the Roseworthy–North Terrace link have been measured.

---

## 2. Project structure and dependencies

### A1. Render pipeline and version
- **[V]** Unity `6000.3.4f1` (revision fdd3b8998ec4): `ProjectSettings/ProjectVersion.txt`.
- **[V]** URP `17.3.0` (`Packages/manifest.json:14`). The default pipeline asset is `Assets/Support/Settings/Project Configuration/Quality URP Config.asset` (`ProjectSettings/GraphicsSettings.asset:43`). A `Performance URP Config.asset` is also present. Both use MSAA 4× and render scale 1.0.
- **[V]** Linear colour space (`ProjectSettings/ProjectSettings.asset:50`, `m_ActiveColorSpace: 1`).
- **[I]** The project was created from Unity's **VR Template**. Evidence: `Assets/Support/VRTemplateAssets/**`, `applicationIdentifier: com.DefaultCompany.VRTemplate` (`ProjectSettings.asset:169`), and tutorial assets.

### A2. XR packages and plug-ins — [V] `Packages/manifest.json`
| Package | Version | Notes |
|---|---|---|
| `com.unity.xr.openxr` | 1.16.1 | Active XR runtime |
| `com.unity.xr.interaction.toolkit` | 3.3.1 | Samples imported are **3.3.0** (`Assets/Samples/XR Interaction Toolkit/3.3.0/`), a minor version mismatch |
| `com.unity.xr.hands` | 1.7.2 | HandVisualizer sample imported |
| `com.unity.xr.management` | 4.5.3 | |
| `com.unity.xr.core-utils` | 2.5.3 | |
| `com.unity.xr.androidxr-openxr` | 1.1.0 | Android XR (not Quest), unnecessary for Quest 3 |
| `com.unity.xr.arfoundation` | 6.3.2 | Not used by project scripts |
| `com.unity.inputsystem` | 1.17.0 | `activeInputHandler: 1` (new Input System only) |
| `com.unity.robotics.ros-tcp-connector` | git URL, **unpinned** | Lock hash `c27f00c6…` in `packages-lock.json` |
| `com.unity.cinemachine` | 2.10.5 | A `CinemachineBrain` exists in the scene; looks vestigial |

- **[V] No Meta XR SDK** (`com.meta.xr.*`), **no Unity WebRTC**, **no Netcode**, and no video or streaming plug-ins.
- **[V]** `Assets/MobileDependencyResolver/` (Google EDM 1.2.185, editor DLLs) is present. Nothing in the project appears to need it. [I]

### A3. OpenXR, Meta Quest and Android build configuration
- **[V]** XR loaders: `Assets/Support/XR/XRGeneralSettingsPerBuildTarget.asset`. **Android and Standalone both use `OpenXRLoader`**, with `m_InitManagerOnStart: 1` for both. A desktop build therefore tries to start OpenXR at launch.
- **[V]** OpenXR features, from `Assets/Support/XR/Settings/OpenXR Package Settings.asset`:
  - Android: **Meta Quest Support enabled** (line 237). Target devices include Quest 3 (`eureka`) and Quest 3S (lines 247–262). Oculus Touch Controller Profile enabled (957). Hand Tracking Subsystem enabled (755). **Android XR Support is also enabled** (484); it is not needed for Quest. [U] Whether this conflicts at build validation is unconfirmed.
  - Android render mode `m_renderMode: 1` = Single Pass Instanced (multiview) (line 1326). Latency optimisation is on. Foveation and SpaceWarp are off.
  - Standalone: Oculus Touch profile (979) and Hand Tracking (308) enabled.
- **[V]** Android player settings (`ProjectSettings/ProjectSettings.asset`): IL2CPP (`scriptingBackend Android: 1`, line 917), Vulkan (`m_APIs: 15000000`, line 586), ARM64 (line 271), minSdk 32 (line 180), `ForceInternetPermission: 0` (line 188), `insecureHttpOption: 2` (line 1024), `runInBackground: 1`.
- **[U]** Whether Unity's automatic Internet permission detection adds `android.permission.INTERNET` for `System.Net.Sockets` use. Check the merged manifest of a Quest build. There is no custom `AndroidManifest.xml`. [V]

### A4. Scene structure and entry points
- **[V]** Build scenes (`ProjectSettings/EditorBuildSettings.asset`): `Assets/Scene/SideQuest_v2.unity` is **enabled**. `SideQuest_v1.unity` is listed but disabled. `Assets/Scene/SampleScene/` holds only lighting data. `Assets/Scene/SideQuestBackUp/` and `Assets/Scene_dst/` are empty.
- **[V]** Top-level hierarchy of `SideQuest_v2.unity`:
  - `Player`: XR rig prefab instance "XR Origin Hands (XR Rig)", from `Assets/Support/VRTemplateAssets/Prefabs/Setup/Complete XR Origin Set Up Hands Variant.prefab`, which derives from the XRI *Hands Interaction Demo* rig. Also `EventSystem` and `Teleport Area Setup/Teleport Area` (teleport locomotion is active).
  - `Interaction/Screen/Content/Video`: **the stereo video surface**.
  - `Interaction/Screen/Content/Zone_Indicator`: zone colour sphere.
  - `Interaction/Screen/Content/Main_Logos`: institutional logos.
  - `Interaction/Console/DockPanel/{ButtonsRow, NotificationBar, BoostModule, LogoPanel}`: control panel UI.
  - `Interaction/Console/{XRUIStateManager, UIAudioPlayer, UIHapticPlayer}`.
  - `Interaction/Robot_Control_Hub`: `RobotCommandPipe`.
  - `Interaction/MusicPlayer`: `MusicDucker`.
  - `Interaction/Archive` (inactive): VR-template video player, interactables, and "Room 2".
  - `Environment/{Terrain, Earth, Dust, Grid, Lighting}`: lunar terrain and Earth.
  - `Room/{Pictures, Screens, Window glass}` plus about 60 sci-fi modular prefab instances: the control-room set, with team photos.
- **[V]** There is no bootstrap or loader script. All behaviour starts from `Start()` and `Awake()` on scene components.

### A5. Assemblies and third-party content
- **[V]** There are no `.asmdef` files for project code. Everything compiles into `Assembly-CSharp`. Project scripts are 11 files in `Assets/Scripts/V4 Two_way/` plus 2 archived receivers in `Assets/Scripts/Archive/`.
- **[V]** Third-party asset packs: `Assets/Downloaded asset packs/{Lunar Landscape 3D, Sci Fi Modular Pack, ScifiOfficeLite}`. Also TextMesh Pro (including Examples), the VR Template assets, and XRI and XR Hands samples. Licences were not audited.

### A6. Missing files and broken references (static) — [V] unless noted
`Library/` is absent, so GUIDs that belong to packages cannot be resolved offline. The findings below cover only GUIDs that should exist under `Assets/`.
1. **18 environment prefabs are missing** (`SM_Trim_Wall_*`, `SM_Ceiling_*`, `SM_Box1`, `SM_Canister1`, `SM_Trim_Floor_8x8M_A3`, and others). They are referenced as `m_SourcePrefab` in both scenes, but no matching asset exists. Their meshes (18 GUIDs) and a shared material (`04b02022…`, 56 references) are also missing. These are room geometry from a sci-fi kit that is not in the repo. Expect missing-prefab placeholders in the control room. This is not critical to streaming.
2. **The project-wide Input Actions asset is missing.** `EditorBuildSettings.asset` points `com.unity.input.settings.actions` at GUID `985fdffe…`, which does not exist. The XRI rig uses `XRI Default Input Actions.inputactions`, which is present. [I] The impact is probably just a warning. [U]
3. **Leftover config objects:** `Unity.XR.Oculus.Settings`, `WindowsMR.Settings`, `ARCoreSettings` and `ARKitSettings` are referenced in `EditorBuildSettings.asset`, but neither the assets nor their packages exist. [I] These are harmless leftovers.
4. **The terrain material template is missing** (`Environment/Terrain`, GUID `594ea882…`).
5. **UI material** `03c5819f…` is missing on 4 slider sub-objects (in the inactive `Archive`), and the **music clip** `364d9f7f…` on the `MusicPlayer` AudioSource is missing.
6. **A broken UnityEvent:** `Interaction/Robot_Control_Hub › RobotCommandPipe.OnZoneChanged` targets the *MonoScript asset* `ZoneReceiver.cs` and calls `set_name`. It should target a component. The zone event therefore does nothing useful (scene line ≈32375).
7. **File and class name mismatch:** `Assets/Scripts/V4 Two_way/ZoneReceiver.cs` declares `class ZoneUIReceiver` (line 4). Unity cannot attach it as a component. No scene instance exists.
8. **Duplicate initialiser:** `AndroidXRSettingsInitializer` exists in both `Assets/XR/AndroidXR/` and `Assets/Support/XR/AndroidXR/`, with different GUIDs.
9. **Dead duplicate receiver:** a second `TogglableReceiver` is attached to the inactive prefab instance `ControlRoom_MonitorV4` (scene line ≈22756).
10. Empty folders: `Assets/Animation`, `Assets/MobileDependencyResolver_dst`, `Assets/Samples/XR 1…8`, `Assets/XR/Settings`.

### A7. Version control and external dependencies
- **[V]** UVCS workspace: `.plastic/plastic.selector` names repository `Side Quest 4/SideQuestXR_Unity@1374526708675@cloud`, branch `/main`. `ignore.conf` excludes Library, Temp, Logs, UserSettings, Build(s), and others. `VersionControlSettings.asset` uses Visible Meta Files.
- **[V]** `GameBuilt/` is a committed Windows x86_64 Standalone build (`Side Quest 4.exe`). It is not covered by `ignore.conf`. Its `Assembly-CSharp.dll` contains the same type names as the repo scripts and nothing more. There is no hidden streaming class and no WebRTC. [V] (string scan)
- **External dependencies outside the repo:**
  - [V] The Pi or host at `169.254.1.10` serving video on 8085 and 8086 (8080 for V1) and commands on 8088.
  - [I] The Dobot control software behind the command hub.
  - [V] The missing sci-fi environment pack.
  - [V] A GitHub fetch for ROS-TCP-Connector on first open.
  - [I] `169.254.x.x` is a link-local address, which implies the Quest or PC and the Pi shared a direct Ethernet or USB link or a single unmanaged LAN. That address is not routable between campuses.

---

## 3. Current stereo streaming pipeline (highest priority)

### B1. Is live stereo streaming implemented?
**Partly.** The Unity **receiver and stereo presentation** are fully implemented. [V] The **capture, stereo pairing, encoding and serving** side is **not in the repository.** [V] A working demonstration needed that external sender.

### B2. Components
| Generation | Script | Material and shader | Transport | Status |
|---|---|---|---|---|
| V1 "Stereo stitch" | `Assets/Scripts/Archive/V1 Stereo stitch/MJPEGReceiver.cs` | `Mat_Video.mat` (URP shader); `FinalStereoGraph.shadergraph` | HTTP MJPEG `GET /cam.mjpg`, port 8080 (line 62) | Archived; not referenced by any scene |
| V2 "Hardware stereo" | `Assets/Scripts/Archive/V2 Hardware_stereo/HardwareReceiver.cs` | `_LeftTex`/`_RightTex` | Framed L/R JPEG over TCP, port 8085 | Archived; superseded by V4 |
| **V4 "Two way" (active)** | **`Assets/Scripts/V4 Two_way/TogglableReceiver.cs`** | **`Assets/Materials/Mat_HardwareStereo.mat` → `DualSourceStereo.shadergraph`** | Framed L/R JPEG over TCP, ports **8085 and 8086** | In use in `SideQuest_v2.unity` |

Active scene object [V]: `Interaction/Screen/Content/Video` has a built-in **Quad** mesh (fileID 10210), scale 752 × 422 (16:9), material `Mat_HardwareStereo`, and `TogglableReceiver` with `piIp: 169.254.1.10` and `currentPort: 8085`. `Stereo3D_Mat.mat` uses the same shader but is not referenced by any scene.

### B3. How left and right streams are received — [V] `TogglableReceiver.ReceiveLoop()` (lines 74–108)
A single TCP connection carries both eyes, interleaved. The wire format is:
```
[1 byte tag: 'L' (0x4C) | 'R' (0x52)] [4-byte big-endian int32 length N] [N bytes JPEG]
```
- Tag read: lines 84–86. Length read with endianness swap: 89–91. Payload read with `BinaryReader.ReadBytes(size)`: 96. Stored in `dataLeft` or `dataRight` under `lock(this)`: 98–101.
- `Update()` (63–72) decodes **only when both eyes have a new frame**, using `Texture2D.LoadImage`, which decodes JPEG on the **main thread**.
- [I] Left and right are paired as "latest L with latest R". There is no timestamp or frame ID in the protocol, so stereo synchronisation depends entirely on the sender emitting matched pairs.
- [I] There is no sanity check on the length field. A corrupt length can trigger a huge allocation.

### B4. Mechanism
**Raw TCP sockets** (`System.Net.Sockets.TcpClient`) on a background `System.Threading.Thread`, carrying a bespoke binary framing of JPEG images. [V] There is no WebRTC, RTSP, WebSocket, Unity networking or native plug-in. [V] V1 used a hand-written HTTP/MJPEG client that scans for JPEG SOI/EOI markers (`MJPEGReceiver.cs:78–101`).

### B5. Eye assignment — [V] `Assets/Scripts/V4 Two_way/DualSourceStereo.shadergraph`
Graph edges (parsed): `Eye Index → Branch.Predicate`; `Sample(_RightTex) → Branch.True`; `Sample(_LeftTex) → Branch.False`; `Branch → BaseColor`. URP Unlit, double-sided.
- Eye Index 0 (left) gets `_LeftTex`. Eye Index 1 (right) gets `_RightTex`.
- Textures are bound in `TogglableReceiver.Start()` (lines 27–28) through `meshRenderer.material.SetTexture`.
- [I] When rendered by a **non-stereo camera**, Eye Index is 0, so the material shows the **left image only**. This matters for the 2D condition (§8).
- V1 equivalent (`FinalStereoGraph`): UV tiling (0.5, 1) with offset x = EyeIndex × 0.5, which splits one side-by-side frame. [V]

### B6. Rectification
**None in Unity.** [V] Both graphs sample the texture directly, with no remap, undistortion or alignment. Whether the sender rectified the images is unknown. [U]

### B7. Resolution, frame rate, buffering and latency
- Initial textures are 1280 × 720 RGB24 (line 24). `LoadImage` resizes to whatever the JPEG is. [V]
- Unity never requests or controls resolution or frame rate. These are set entirely by the sender. [V]
- Buffering is a single slot per eye that is overwritten (latest wins). Stale frames are dropped implicitly. [V] TCP backpressure falls on the sender. [I]
- There is no latency measurement, timestamping or frame-rate display. [V]
- [I] Decoding two JPEGs per frame on the Quest main thread will cost CPU time and may limit frame rate or cause judder at higher resolutions. [U] Profile on device.

### B8. Disconnection and reconnection
- [V] Any exception, or end of stream, ends `ReceiveLoop`. It logs a warning (`"V3 Switcher Error"`, line 104) and the thread exits. **There is no automatic reconnection.** The last frame stays on screen with no "signal lost" indication.
- [V] `SwitchCameraSource()` returns early if the port has not changed (line 36), so pressing the same camera button does not reconnect.
- [V] Stopping a stream uses `Thread.Abort()` (line 59). [U] `Thread.Abort` behaviour under IL2CPP on Android must be tested. [I] If the abort does not take effect, the old thread survives with `isRunning` set back to `true`, and two threads write to the same buffers. That could interleave frames from two cameras.

### B9. Changing the source dynamically
**Yes, by port.** [V] Scene wiring, reconstructed from prefab overrides:
- `Button_TopView` → `TogglableReceiver.SwitchCameraSource(8086)` on `…/Video` (PrefabInstance 8120008007635989748). It also calls `UIAudioPlayer.PlaySecondary` and `UIHapticPlayer.BuzzClick`.
- `Button_SideView` → `SwitchCameraSource(8085)` (PrefabInstance 378450602).
- The host IP is a serialized field and cannot be changed at runtime. Each source is its own stereo stream on its own port. [V]
- `XRUIStateManager` labels these buttons "Camera Inspector" (TopView) and "Camera Manager" (SideView) in comments (lines 17–18). They are shown only in the Running and FixMode states.

### B10. Presentation
A **flat, floating, world-space quad** with a per-eye texture. It is a "stereo window" and not a panorama or a stereo layer. [V] There is no compositor-layer use (for example OpenXR quad layers) and no head-locked screen. [V]

### What is code, scene configuration, or external
| Aspect | Code | Scene config | External |
|---|---|---|---|
| TCP receive and decode, eye routing | ✔ | | |
| IP address, ports, quad size and position, material | | ✔ | |
| Camera capture, stereo pairing, JPEG encoding, serving | | | ✔ (not in repo) |
| Rectification and calibration | | | ✔ if any [U] |

---

## 4. XR rendering and interaction

- **XR rig and head tracking** [V]: `Player/XR Origin Hands (XR Rig)`, from `Complete XR Origin Set Up Hands Variant.prefab` and then XRI `Hands Interaction Demo/Prefabs/XR Origin Hands (XR Rig).prefab`. It provides XRI 3.3 tracked-pose camera, controllers, hands, a tunnelling vignette (`TunnelingVignette.prefab`), and affordance callouts. Teleport locomotion is active (`Player/Teleport Area Setup/Teleport Area`, `TeleportationArea`).
- **Controller interaction** [V]: the Oculus Touch interaction profile and Hand Tracking are enabled. XRI ray and poke interactors come from the sample rig. Input comes from `XRI Default Input Actions.inputactions`.
- **UI panels** [V]: 4 world-space canvases (`m_RenderMode: 2`) and 2 screen-space canvases. A `TrackedDeviceGraphicRaycaster` is present, so XR rays can drive standard uGUI `Button`s. The control panel is `Interaction/Console/DockPanel` (`ButtonsRow`, `NotificationBar` with `StatusLabel`, `CountdownLabel` and `TimerLabel`, `BoostModule`, `LogoPanel`).
- **UI state machine** [V]: `XRUIStateManager.cs` has states `Boot`, `Starting`, `Running` and `FixMode` (line 8). `ApplyState()` (420–474) shows and hides buttons. `UpdateButtonInteractivity()` (503–533) gates FIX and DROP on a `DECISION_READY` window. `DEV_MODE` reveals Home, Cancel and Gripper buttons (476–485).
  - START is blocked until the server sends `NAME_SET` (`OnStartClicked`, line 112). Without the server, the UI stays at "Waiting for player name..." for good.
  - `FixAckTimeoutSeconds` (line 44) is declared but never used, so a lost FIX ACK leaves FIX disabled.
- **Camera selection**: see B9.
- **Voice or speech**: **none.** [V] No speech, Whisper, keyword recogniser or microphone code.
- **Input architecture** [V]: everything is uGUI `Button.onClick` persistent calls wired in the scene. There is no central input or command layer.
- **Robot commands initiated from XR** [V]: Start → `XRUIStateManager.OnStartClicked`, which runs a 3 s countdown and then `RobotCommandPipe.SendStart()`. Drop → `OnDropClicked` + `SendDrop()`. Fix → `OnFixClicked` (bound **twice**; the second call is blocked by the pending guard). Nudge L/R/F/B → `RobotCommandPipe.NudgeLeft/Right/Up/Down` (Forward and Back are also sent from `XRUIStateManager`; the 300 ms cooldown suppresses the duplicate). Dev buttons → `SendHome`, `SendCancel`, `SendGripToggle/Open/Close`. **Note:** a prefab instance named `BG_Circle` also calls `SendGripOpen` (PrefabInstance 2129793429). It looks accidental and should be checked. [I]
- **Feedback and indicators** [V]:
  - `ZoneIndicator` (`Interaction/Screen/Content/Zone_Indicator`): tints a sphere GREEN, YELLOW or RED from `ZONE <colour>` messages (`ZoneIndicator.cs:62–80`). A second `ZoneIndicator` on `Interaction/Screen` has no references and does nothing.
  - `UIAudioPlayer.ResolveDropClip()` (lines 96–107) plays **zone-specific drop sounds**, triggered from `XRUIStateManager.OnDropAck()` (261–267).
  - `BoostUIController` (combo lights, pulsing frame), `MusicDucker`, run timer, "GAME OVER".
  - `XRUIButtonFeedback` (press scale, click audio, haptics) and `UIHapticPlayer` (XRI `HapticImpulsePlayer` on both controllers).

---

## 5. External services and robot integration

- **Protocol** [V]: plain TCP to `169.254.1.10:8088` (`RobotCommandPipe.cs:12–13`). UTF-8, newline-delimited ASCII lines.
- **Unity → hub** [V] (`RobotCommandPipe.cs:319–378`): `START`, `DROP <seq>`, `COMMIT <seq>` (defined but unused), `FIX <seq>`, `CANCEL`, `HOME`, `GRIP_TOGGLE`, `GRIP_OPEN`, `GRIP_CLOSE`, `NUDGE <dx> <dy>`.
  - Units are inconsistent: dx = ±`nudgeStep` (the scene sets 1, and the field is labelled mm), but dy is always ±1. [V]
- **Hub → Unity** [V] (`HandleIncomingLine`, lines 183–313): `ZONE GREEN|YELLOW|RED`, `RUN_COMPLETE`, `RUN_FAIL TUMBLE`, `NAME_SET`, `DECISION_READY <seq>`, `BOOST_STATE <combo> <0|1>`, `BOOST_END`, `ACK START|DROP|FIX`, `NACK <cmd> <reason>`.
- **Acknowledgements** [V]: START, DROP and FIX are acknowledged. START has a 5 s timeout (`startAckTimeoutSeconds`). FIX has none in practice. NUDGE, HOME, CANCEL and GRIP are fire-and-forget. A decision token (`_latestDecisionSeq`) ties DROP and FIX to the server's current decision point. This is a good pattern for AI2 decisions.
- **State synchronisation** [V]: event-driven only. There is no robot pose, joint state, heartbeat or connection-status UI. `currentZone` is the only persistent state.
- **ROS / rosbridge** [V]: ROS-TCP-Connector is installed and `Assets/Support/Resources/ROSConnectionPrefab.prefab` is configured (127.0.0.1:10000, ConnectOnStart). **No script references `ROSConnection`** and no ROSConnection is in the scenes. [I] It is unused. No rosbridge, WebSocket or HTTP is used. There are **no Dobot references** anywhere in Unity assets. [V]
- **Running without the robot** [V/I]: the scene will render, the receivers fail quietly, and the UI stays in Boot.
  - **Caveat:** `RobotCommandPipe.Connect()` uses the **synchronous** `new TcpClient(host, port)` on the **main thread** (line 98) and retries every second from `Update()` (82–86). [I/U] If connection attempts time out instead of failing fast, which depends on the network, this can stall frames in the headset. That is a comfort risk in XR.

---

## 6. Reusable component inventory

### 1. Reusable with little or no change
| Component | Evidence | Notes |
|---|---|---|
| URP + OpenXR + Quest 3 build configuration | §A3 | Remove Android XR Support; set a real `applicationIdentifier` |
| XRI 3.3 rig, uGUI ray interaction, haptics (`UIHapticPlayer`, `XRUIButtonFeedback`) | §4 | Disable teleport for seated supervision |
| `DualSourceStereo.shadergraph` / `Mat_HardwareStereo.mat` | §B5 | Per-eye texture selection works under Single Pass Instanced. [U] Test on device |
| Lunar environment (`Environment/Terrain`, `Earth`, `Dust`; `Lunar Landscape 3D`) | §A4 | Fits the "restrained lunar setting". Fix the missing terrain material |
| `UIAudioPlayer` click and hover sounds (not the zone sounds) | §4 | |

### 2. Reusable with modification
| Component | Required changes |
|---|---|
| `TogglableReceiver` | Configurable host as well as port; automatic reconnect with backoff; clean shutdown (close the socket instead of `Thread.Abort`); a frame-ID or timestamp field for latency and logging; a length sanity check; a "no signal" state; possibly off-main-thread decode or hardware decode |
| L/R framed-JPEG protocol | Usable for Milestone 1 on a LAN. Extend the header with sequence number, capture timestamp and camera ID |
| `RobotCommandPipe` (as a backend client) | Asynchronous connect; replace Dobot-game vocabulary with AI2 messages; keep the line-protocol, ACK/NACK, decision-token and main-thread-queue patterns |
| `XRUIStateManager` | Keep the state-machine skeleton and decision-window gating. Replace the states and buttons with AI2 (Allow / Inspect / Intervene); remove the name gating and countdown; implement the FIX-style ACK timeout |
| Camera-switch buttons (`Button_TopView`/`Button_SideView`) | Rename to wrist/overview; drive through a source-selection API instead of hard-coded ports |
| `Interaction/Screen` video quad | Geometry is fine. Add an Inspect zoom (a UV scale/offset uniform in the shader) and a frame or status overlay |
| Control-room set | Strip the institutional and team imagery and the missing SM_* geometry; keep the restrained elements |

### 3. Unsuitable for Phase 2
| Component | Reason |
|---|---|
| `ZoneIndicator`, `ZONE` messages, zone-coloured drop sounds (`UIAudioPlayer.ResolveDropClip`, `OnDropAck`) | **Direct placement-correctness cues.** Remove entirely |
| `BoostUIController`, `BOOST_*`, `MusicDucker`, combo, "GAME OVER", run timer | Gamification; adds confounds |
| Nudge and gripper controls, `HOME` and `CANCEL` buttons, `NUDGE` command | Direct teleoperation, not supervision. Keep, if at all, only as experimenter tools |
| `NAME_SET` start gating, start countdown | Specific to the demo's player flow |
| Archived V1 MJPEG and V2 receivers, `FinalStereoGraph` | Superseded |
| ROS-TCP-Connector, AR Foundation, Android XR, Cinemachine, Mobile Dependency Resolver | Unused. Remove to reduce build risk (decision for later) |
| Hard-coded `169.254.1.10` addressing | Not routable between CRATER and North Terrace |

### 4. Missing and requiring new development
- **The CRATER-side camera service:** DepthAI capture from 2 × OAK-D Pro PoE, stereo pairing, encoding, serving, and multi-client fan-out.
- The **experiment-control backend** (AI2 decision points, robot-orchestration bridge to the UR20, session management).
- **Event logging** with synchronised timestamps (participant actions, decision latency, video frame IDs), and **questionnaires**.
- The **2D desktop client** (scene, input, layout).
- **Digital zoom** during Inspect.
- Minimal **task and robot status** panel (participant-safe, with no correctness cues).
- **Latency instrumentation** (glass-to-glass, network RTT) and connection-health UI.
- Remote networking: routing, VPN or firewall, and bandwidth budget between Roseworthy and North Terrace.
- Calibration and rectification policy, and an IPD / stereo-window configuration for the XR view.

---

## 7. Missing dependencies and uncertainties

| # | Item | Status |
|---|---|---|
| 1 | Pi or host video sender (ports 8080/8085/8086) and command hub (8088): source, language, camera hardware, encoding parameters, whether it rectified, whether it accepted several clients | Not in repo [V]; behaviour [U] |
| 2 | Original stereo camera hardware ("Hardware_stereo") | [U] |
| 3 | Dobot control stack and how DECISION_READY and ZONE were computed | [U] |
| 4 | 18 SM_* environment prefabs, their meshes and material `04b02022…` | Missing [V] |
| 5 | Project-wide Input Actions asset `985fdffe…` | Missing [V] |
| 6 | Terrain material template, music clip, one UI material | Missing [V] |
| 7 | Package GUID resolution (Library absent): whether all package scripts resolve on first import, especially the unpinned ROS-TCP-Connector git dependency | [U] Needs Unity open |
| 8 | `Thread.Abort` under IL2CPP/Android; main-thread JPEG decode cost on Quest 3; Eye Index under Vulkan multiview | [U] Needs a device test |
| 9 | Android INTERNET permission in the merged manifest | [U] |
| 10 | Whether `GameBuilt/` matches the current scene state | [I] Same script type set; scene parity [U] |
| 11 | **OAK-D Pro (PoE) stereo-pair characteristics.** From vendor documentation, not this repo: the stereo pair is normally **monochrome global-shutter** sensors (with the colour camera central), and Pro models add an **IR dot projector** that would appear in stereo imagery if enabled | [U] Confirm against Luxonis documentation and your specific SKUs |

---

## 8. Recommended Phase 2 architecture

### 8.1 Data flow (target)
```
 CRATER, Roseworthy                                          North Terrace, Adelaide
 ─────────────────────────────────────────────               ───────────────────────────────────────
 OAK-D Pro PoE (wrist)  ─┐  PoE/GigE                          ┌──────────────────────────────────┐
 OAK-D Pro W PoE (tripod)┴──► Camera Gateway (DepthAI host)   │ Condition B: Quest 3 (Unity APK) │
                              • L/R capture, (rectify?)       │  StereoReceiver → per-eye quad   │
                              • encode (JPEG now; H.264 later)│  AI2 UI · zoom · status          │
                              • per-frame seq + timestamp     │                                  │
                              • fan-out to N clients ─────────┼──► (same stream, both eyes)      │
                                         │     campus WAN/VPN │                                  │
 UR20 controller ◄── Robot Bridge ◄──────┤                    │ Condition A: Desktop (Unity exe) │
   (RTDE / URScript; not Unity)          │                    │  same StereoReceiver → LEFT only │
                                         ▼                    │  AI2 UI · zoom · status · forms  │
                              Experiment-Control Backend ◄────┼──── commands / events (TCP/WS)   │
                              • AI2 decision points, tokens   └──────────────────────────────────┘
                              • ACK/NACK, session state
                              • authoritative event log  ──► log store (CSV/JSONL/DB)
```
Today's equivalent, for contrast:
`Pi @169.254.1.10 ──TCP:8085/8086 [L|len|JPEG][R|len|JPEG]──► TogglableReceiver ► Mat_HardwareStereo (EyeIndex)` and `RobotCommandPipe ◄─TCP:8088 ASCII lines─► Pi command hub ► Dobot`.

### 8.2 2D client: Unity desktop, browser, or something else?

**Recommendation: Unity desktop (Windows Standalone) built from the same project.** [I] The reasons are drawn from the repository:
1. **Identical image path.** The same `TogglableReceiver`-derived receiver, the same `LoadImage` decode and the same material. Rendered by a non-XR camera, `DualSourceStereo` shows Eye Index 0, which is the left image (§B5). Resolution, compression, colour, frame pacing and latency are then the same in both conditions, and stereopsis is the only intended difference. A browser client would need a different transport, decoder and timing, which would add confounds.
2. **Browsers cannot open raw TCP sockets.** The existing protocol (§B3) would need a WebSocket, HTTP-MJPEG or WebRTC gateway. That is a second pipeline to build, validate and match for latency.
3. **Shared logic.** AI2 state machine, zoom, status panel, logging client and backend client can be written once in C# and used by both builds. Separate scenes keep the presentation independent.
4. **Configuration is already close.** A Standalone XR loader exists. For the 2D build, set "Initialize XR on Startup" off for Standalone (`XRGeneralSettingsPerBuildTarget.asset` currently has it on), or use a separate build profile.

**When a browser would be preferable:** if the transport moves to WebRTC for both clients (for WAN robustness, H.264 hardware decode and NAT traversal), a browser 2D client becomes reasonable. The Quest client would then need Unity WebRTC or a native decoder, neither of which is present. Treat this as a Milestone 2+ decision, made after measuring latency and bandwidth.

### 8.3 Streaming transport
- **Milestone 1:** keep the existing L/R-JPEG TCP framing and write a new DepthAI sender that emits it. Optionally extend the header to `[tag][cam_id][seq u32][t_capture u64][len][JPEG]`; this needs a matching small receiver change. [I] This has the lowest risk and reuses the Unity receiver almost unchanged.
- **Bandwidth caution** [I]: two 720p JPEG streams per stereo source at 30 fps is likely to be tens of Mbit/s. Measure it on the inter-campus path before committing. If it is too high, move to H.264 encoded on the OAK (on-device VPU encoder; [U] confirm stereo-pair encoding support) carried over WebRTC or RTP, with decode on Quest.
- The sender must **fan out** to at least the active participant client and an experimenter monitor. [U] Whether the original Pi sender could do this is unknown.

### 8.4 Backend
- Replace the Pi command hub with an **experiment-control backend** that owns AI2 decision points, issues decision tokens (the same pattern as `DECISION_READY <seq>`), ACKs participant actions, forwards approved actions to a separate UR20 bridge, and writes the authoritative timestamped event log.
- Clients reuse the `RobotCommandPipe` patterns: main-thread queue, ACK/NACK, token. Connection must be asynchronous, and the message set is new (for example `ALLOW <seq>`, `INSPECT_BEGIN/END <cam>`, `INTERVENE <seq> <reason>`, `CAMERA <id>`, `ZOOM <level>`). JSON lines over TCP or WebSocket would be easier to log and version than bare tokens. [I]
- **Participant safety rule:** no message that carries correctness information (anything like `ZONE`) may reach participant clients.

---

## 9. Proposed first implementation milestone

**Goal:** the same live stereo camera source shown in Quest 3 (stereo) and on a desktop (monocular, left eye) at the same time.

**Scope (no AI2, robot or logging yet):**
1. **Camera gateway (new, outside Unity):** a DepthAI script on a lab PC with one OAK-D Pro PoE. It outputs left and right frames as JPEG in the existing framing (`'L'|BE-len|JPEG`, `'R'|BE-len|JPEG`) on one TCP port, accepts **two simultaneous clients**, and disables the IR projector. It records the resolution, frame rate, JPEG quality and whether frames are rectified.
2. **Unity, new minimal XR scene** (a copy, not an edit of `SideQuest_v2`): XR rig with teleport off, lunar environment, one video quad using `Mat_HardwareStereo`, and a receiver derived from `TogglableReceiver` with a configurable host, reconnect and "no signal" state. No `RobotCommandPipe`, zone, boost or music components.
3. **Unity, new desktop scene and build:** a standard camera facing the same quad and material (Eye Index 0 gives the left image), or a `RawImage` bound to the left texture. Standalone build with XR initialisation disabled.
4. **Wrist and overview switch:** two sources on two ports, using the existing `SwitchCameraSource` mechanism (or two simultaneous connections), with identical switching in both clients.
5. **Measurement:** on-screen frame rate and frame age if the extended header is used, and a glass-to-glass latency test (for example a timer filmed through the camera) for both clients, on the lab LAN and then over the inter-campus path.

**Acceptance criteria:**
- Both clients show the same live source at the same time.
- The Quest shows correct eye assignment (a left/right swap test with an occluder).
- Both clients recover automatically after the sender restarts.
- Latency, frame rate and bandwidth are measured and recorded for both conditions.

---

## 10. Questions requiring researcher input

1. **Image type for stereo:** the OAK-D Pro stereo pair is (by vendor specification, to confirm) monochrome. Is greyscale stereo acceptable, or must the stimulus be colour? This decides whether both conditions use the mono pair, or a colour source plus a different stereo strategy. Using the **left mono camera for 2D** keeps the two conditions matched.
2. **Monocular source for Condition A:** the left eye of the same stereo pair (recommended for matching), or the central RGB camera?
3. **Rectification and calibration:** should rectification happen on the OAK, on the gateway, or not at all? What virtual screen distance and size should be used for comfortable, scaled disparity in XR?
4. **Inspect zoom in stereo:** digital zoom scales disparity as well. Should XR zoom be applied identically to both eyes, and should zoom be matched across conditions in field of view or in magnification?
5. **Network:** what connectivity exists between CRATER and North Terrace (bandwidth, latency, VPN, firewall)? Is a dedicated link or local relay possible?
6. **Original Pi software:** can the Side Quest sender and command-hub source be recovered? It would clarify the original encoding, pairing and multi-client behaviour.
7. **AI2 semantics:** what exactly do Allow, Inspect and Intervene trigger on the UR20 (pause, retry, skip, abort)? Who decides when a decision point opens? Is there a timeout or default action?
8. **Task and robot status:** which minimal status fields are permitted (step number, robot moving/paused, time remaining) without revealing placement correctness?
9. **Questionnaires:** in-application (in-headset for XR, which risks a modality confound) or administered outside both conditions in the same way?
10. **Logging:** required event schema, clock-synchronisation precision, and storage location (backend only, or also client-side).
11. **Environment:** for the "restrained lunar" XR setting, should the control-room set be removed entirely (terrain, Earth and console only), and should institutional and team imagery be excluded?
12. **Version control:** create a new UVCS branch or repository for Phase 2 (for example `<name>_phase2_minimal`, following the README convention), and who maintains merges now?

*Audit complete. No project files were modified. Awaiting instructions before implementation.*
