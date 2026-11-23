# Task 05: Unity Windows reception — implementation plan

**Status (5 Nov 2026):**
- **Approved for M1 preparation** (researcher decisions, §10).
- **Compatibility milestone complete, offline only** (§12): project created; FFmpeg path verified in the Editor and in a Windows standalone player.
- **M1 offline implementation complete (5 Nov, §13).** Every offline check passes in the Editor and the Windows player. The M1 criteria are not yet scored (they need T4). Live tests need separate approval.

**Corrections from the compatibility work:**
- The BtbN LGPL build is **LGPL-3.0-or-later**, not 2.1 (§3).
- Unity's Mono `Stopwatch` is **not** the QPC clock Python uses (§4.6).
- The end-of-frame marker for frame N travels in frame N+1's packet (§4.1).

**Inputs:**
- the [provisional architecture](../architecture/Phase2_Provisional_Architecture.md) (D4: one Unity codebase, receiver behind `IStereoVideoSource`);
- the [Task 04A audit](../audits/Phase2_Task04A_Streaming_Architecture_Audit.md) §5 and §7 (G2 gate);
- the [COROL addendum](../audits/Phase2_Task04A_Addendum_COROL_Integration_Audit.md) §9 (event-record format);
- the [Side Quest audit](../audits/SideQuest_Phase2_Technical_Audit.md) §3 and §6;
- the Task 04B code and results ([streaming_poc](../../streaming_poc/README.md); checkpoint §13.3–13.10).

**Labels:** **[V]** verified (measured, or read in source / on this machine); **[I]** inferred; **[U]** unverified, to be checked in the step named.

---

## 1. Summary

- **Goal of the first milestone (M1):** one synthetic camera (A) received in a Windows Unity scene from the existing localhost MediaMTX.
  - Both eye paths are received and **paired by sequence number**; the left eye is displayed, as in the 2D condition.
  - Capture → display frame age is measured, and the stream recovers reliably after a stall and after a server restart.
- **Recommended decoder route:**
  - **FFmpeg 9.0 (LGPL shared build)**, called from C# through **FFmpeg.AutoGen 9.0.x (MIT)**;
  - one reader/decoder thread per eye;
  - the decoded luma plane uploaded to an `R8` texture on the main thread.
  - **Why this route:**
    - It uses the same FFmpeg 9.0 demuxer, parser and decoder as the Python reference receiver that passed G1, so G1 and G2 differ only in the receiver host.
    - It needs **no C++ toolchain**, which this laptop does not have [V].
- **The Python reference receiver is a specification, not a component.** Its pairing, freshness, freeze and reconnect behaviour is ported to C#, and tested against the same scenarios and the same log schema, so the existing analysers can score Unity runs.
- **Quest 3 (later, gate G3):** the C# core (metadata, pairing, freshness, logging, reconnect state machine, texture and shader path) carries over. Only the transport/decoder back-end is replaced (§6).

## 2. Starting point (facts)

| Item | State |
|---|---|
| Unity | **6000.3.28f1 (6.3 LTS)** at `C:\Program Files\Unity\Hub\Editor\6000.3.28f1` [V]. URP test project opens and Play Mode works (researcher). `PlaybackEngines\windowsstandalonesupport` present [V]. `AndroidPlayer` with `SDK`, `NDK` and `OpenJDK` folders present [V], but Android Build Support and Quest deployment are **not verified** |
| Disposable test project | `Phase2_Interface\My project` (6000.3.28f1 [V]). **Not used and not modified** |
| Recovered Side Quest project | 6000.3.4f1, URP 17.3, OpenXR, IL2CPP + Vulkan on Android, Single Pass Instanced. Receiver: L/R JPEG over TCP, no metadata, no reconnect, `Thread.Abort` (Side Quest audit §B3–B8). **Read-only.** Opening it in 6000.3.28f1 would upgrade it, so it is not opened. Assets are copied later if needed (§6) |
| Build tools on this laptop | No Visual Studio / MSVC, no CMake, no .NET SDK [V]. Unity compiles C# itself |
| Reference stream | `publish_synthetic.py`: H.264 Constrained Baseline, 1280 × 800, 20 fps, 8 Mbit/s per eye, 1 s keyframe interval, two RTSP paths per camera (`camA_left`, `camA_right`). The FrameMeta v1 SEI goes before the first slice, and the end-of-frame SEI after the last slice (`--frame-end sei`) [V] |
| FrameMeta v1 (SEI user-data-unregistered, UUID `6b3f0c1e-04b0-4c2a-9a51-7e2d5a0f4b11`) | Little-endian `<BBBBQqqqI16s16s16s` + CRC-32 (88 + 4 = 92 bytes): `version, camera, eye, flags, seq, t_dev_ns, t_host_mono_ns, t_utc_ns, config_id, host, session, trial` (`poc_common.FrameMeta`) [V] |
| Reference receiver settings | RTSP/TCP; `fflags nobuffer`, `flags low_delay`, `max_delay 0`, `reorder_queue_size 0`, probesize and analyzeduration 500,000; decoder `thread_count 1`. Presenter: 60 Hz display; freeze > 125 ms; excess-delay limit 100 ms over a 10 s window; 20 warm-up pairs; re-baseline after 2 s; reconnect backoff 0.25 s doubling to 1 s (`receive_reference.py`) [V] |
| Lessons carried over | FFmpeg's H.264 parser holds each frame until the next one unless a frame-end NAL follows (checkpoint §13.4) [V]. Reconnect must not hold stale data (P2 fix) [V]. All processes must exit before cleanup checks (S8 fix) [V] |
| FFmpeg used by the reference | PyAV 19.0.2 bundles **FFmpeg 9.0.2** (libavcodec 63.1.102) [V] |

## 3. Decoding approaches and licensing

**Why not embed Python/PyAV:**
- Unity runs C# on Mono (Editor and Windows) or IL2CPP (required for Android). There is no CPython.
- Embedding CPython (e.g. pythonnet) would add a second runtime with its own GIL and garbage collector, and a Python installation inside the build. It would not work in an IL2CPP Android build, so it would split the 2D and XR conditions.
- The behaviour is ported instead. The FFmpeg library underneath PyAV is called directly.

| Approach | Licence / cost | RTSP | Per-frame SEI access | Toolchain on this laptop | Quest reuse | Verdict |
|---|---|---|---|---|---|---|
| **FFmpeg (libavformat + libavcodec) via FFmpeg.AutoGen, C# `unsafe` interop** | Bindings **MIT** (changed from LGPL) [V]; the BtbN `win64-lgpl-shared` FFmpeg is **LGPL-3.0-or-later** (`--enable-version3`; no GPL or non-free parts) [V, compatibility milestone] | Yes, the same demuxer as the reference | Yes: SEI read from `AVPacket` bytes before decode, exactly as in Python | None needed (prebuilt DLLs + managed DLL) | Managed code reusable; an Android FFmpeg build would need the NDK [U] | **Recommended for M1** |
| FFmpeg via our own C++ native plugin | LGPL FFmpeg; our code | Yes | Yes | **Needs MSVC + CMake** (install approval, possibly admin) | C++ portable to the Android NDK | Fallback if managed interop proves too slow or fragile |
| GStreamer native plugin (appsink → texture) | LGPL core; plugin licences mixed | Yes | Needs a parser probe [U] | Needs a C toolchain and a GStreamer runtime install | Android binaries exist | Alternative; heavier |
| Windows Media Foundation H.264 decoder + a C# RTSP/RTP client | Decoder licensed with Windows | Client to write or adopt | Yes (we see the NALs) | COM interop; no compile needed | Decoder Windows-only | Not for M1 |
| VLC for Unity (LibVLC) | Commercial plugin; the vendor lists a $700/year subscription | Yes | No per-frame metadata access [I] | Plugin | Yes | Not recommended (no SEI; player-style buffering) |
| AVPro Video | Commercial | RTSP not documented, per a competitor's comparison [U] | No [I] | Plugin | Yes | Not recommended |
| Unity `VideoPlayer` | Built in | **No RTSP** (vendor guide; consistent with Unity docs [I]) | No | — | — | Excluded |
| Unity WebRTC | Deprecated (Task 04A) | — | No | — | — | Excluded |

**Licensing obligations for the recommended route** (practical summary, not legal advice; the university's research-office guidance takes precedence):
1. **Keep the LGPL build separate.**
   - Use the FFmpeg **LGPL** variant only (the BtbN build is LGPL **3.0**-or-later, verified), kept as **separate, replaceable DLLs** (dynamic linking) next to the executable.
   - At startup, log `avutil_license()` and `avcodec_configuration()`, and **refuse to start** unless the licence string is LGPL. This guards against an accidental GPL build.
2. **Keep the required notices.**
   - Ship FFmpeg's licence text, the exact build name and commit, and a pointer to the corresponding source.
   - Keep the FFmpeg.AutoGen MIT notice.
3. **No GPL encoders on the client.** libx264 (GPL) stays only on the synthetic publisher side, in the PyAV wheel, and is never distributed with the Unity client.
4. **University licensing review before any distribution outside the lab** (researcher decision 12, 5 Nov). It covers the LGPL-3.0 terms, the bundled libraries' notices and H.264 patents. Details are in `unity/Phase2Client/ThirdParty/README.md`.
5. **H.264 patents:** AVC decoding is covered by a patent pool (Via LA). The Windows and Android built-in decoders are licensed through the OS and device; a software libavcodec decoder is not. For internal, non-commercial research use this is usually treated as low risk, but **flag it to the university** if the client is distributed outside the lab.

## 4. Recommended Windows design

```
 MediaMTX (localhost)          Unity Windows client (one process)
 camA_left  --RTSP/TCP-->  [EyeReader L thread]  open/read with timeouts + interrupt flag
                              av_read_frame -> SEI FrameMeta (CRC) -> avcodec decode (1 thread)
                              -> copy Y plane into pooled buffer -> barcode check -> push(L, meta, buf)
 camA_right --RTSP/TCP-->  [EyeReader R thread]  (same)                              \
                                                                                      v
                           [StereoPresenter] (pure C#; port of receive_reference.Presenter)
                              newest complete pair by seq; excess-delay rejection; obsolete backlog;
                              freeze detection; warm-up / rebaseline / reconnect reset
                                                                                      |
 main thread (Update) ----> tick(now) -> chosen pair -> LoadRawTextureData into R8 textures (L, R)
                              -> material (left eye in 2D; per-eye later in XR) -> log display row
 background log writer <--- events.jsonl, frames.csv, arrivals.csv, summary.json (reference schema)
```

### 4.1 Transport and decode (per eye, background thread)

- **Open:** `avformat_open_input` with **the same options as the reference** (§2), plus I/O timeouts (`timeout`) and an `AVIOInterruptCB` that checks:
  - a shutdown flag;
  - the open deadline (3 s) and the read deadline (3 s).

  The callback must be a static method marked `[MonoPInvokeCallback]` with a rooted delegate, so it is IL2CPP-safe [I].
- **Decode:** H.264 software decoder, `thread_count 1`, slice threading only. Frame threading would add frames of delay [I]; the reference measured 0.9 ms median decode [V].
- **Frame-end dependency:** the parser holdback is avoided only if the sender appends the end-of-frame SEI.
  - **Placement [V, compatibility milestone]:** the marker after frame N's last slice becomes the first NAL of the next access unit. Frame N's packet therefore carries the marker of N−1, and the last frame's marker arrives in a trailing slice-less packet. The Python `arrivals.csv` shows the same pattern (`eof_seq` = seq − 1).
  - The reader logs whether frame-end markers are present.
  - M1 tests always run the publisher with `--frame-end sei`; the OAK gateway must do the same later (Task 04).
- **Backlog:** the reader always drains the socket at network rate and never waits for the main thread, so no TCP backlog builds behind a slow frame. Decoded frames go into a small per-eye pool (about 8 buffers); when it is full, the oldest is recycled and counted.
- **No Unity API calls off the main thread.**

### 4.2 Metadata, frame IDs and integrity

- The SEI is parsed **from the packet bytes before decode**, as in Python:
  - Annex-B split;
  - emulation-prevention removal;
  - `user_data_unregistered` with our UUID;
  - FrameMeta v1 unpack;
  - CRC-32 check;
  - version and camera/eye validation.
- Any error is logged as `sei_error` and the frame is not displayed.
- **Picture/metadata consistency:** the burned-in barcode (sequence, eye, camera) is read from the CPU luma copy, the same check as the reference. A mismatch is an `integrity_error`.
- **Nothing in the display path depends on decoder side-data or PTS.** The sequence number and capture times come only from the SEI.

### 4.3 From decoded frame to Unity texture

- **Format:**
  - The synthetic frames, and the OAK rectified mono outputs, are greyscale; only the **Y plane** is needed.
  - Use `Texture2D(1280, 800, TextureFormat.R8, mipChain: false, linear: true)` per eye, with no mipmaps, bilinear filtering and clamp wrapping.
- **Upload:** on the main thread, `LoadRawTextureData(IntPtr, size)` + `Apply(false)`, about 1 MB per eye per new pair (20 Hz). A row-stride copy is needed when `linesize ≠ width`.
  - **Expected cost:** small [I]; it is measured in M1 (Unity frame-time criterion M1.8).
  - **Upgrade path if needed:** a render-thread upload through a native rendering plugin. This needs the C++ toolchain, so it is deferred.
- **Colour:**
  - The luma values are display-referred (gamma-encoded). The project is in linear colour space, so the shader converts the sampled value from sRGB to linear before output; it is not treated as linear data.
  - Verified by the PSNR criterion against the source frame (M1.9; G2 requires ≥ 40 dB).
- **Shader:** a new URP unlit shader. Its inputs are:
  - `_LeftTex`, `_RightTex`;
  - an eye-select mode (2D: left; XR: by `unity_StereoEyeIndex`, the same logic as Side Quest's `DualSourceStereo`, re-implemented rather than copied for M1);
  - a **UV crop rectangle** (Camera A's crop `img[6:776, 39:1277]` belongs to the full G2; for M1 it is present but set to the full frame).
    - **Erratum (6 Nov 2026, Task 06):** this is not what was implemented. `DisplayRig.CameraACrop = RectInt(39, 6, 1238, 770)` is applied whenever the camera is A, so T3, T4 and every replay displayed the crop. T4's render check verified 1238 × 770 pixels pixel-exact. Only the exact crop *check* against real imagery belonged to G2.
- **Colour later:** if a colour source is ever used, the NV12 Y and UV planes go into two textures with conversion in the shader. That is not needed for the approved mono pipeline.

### 4.4 Pairing, freshness, backlog dropping and freezes

`StereoPresenter` is a line-by-line port of `receive_reference.py`'s presenter (the specification), with the same parameters and defaults. At each Unity frame (`Update`), it does the following:
1. **Pick** the **newest sequence number for which both eyes have arrived.** It never shows an unmatched pair; an incomplete newer frame waits within the pairing window.
2. **Measure excess delay.** The pair's relative delay is (receiver UTC when the pair completed − sender UTC capture time), minus the minimum over the last 10 s. If the excess is over 100 ms, the pair is rejected, together with the older queued pairs (the obsolete backlog). The last good image stays, and the reason is logged.
3. **Label** the pair "fresh" only after warm-up, or after a trusted-clock absolute check (same host: shared QPC clock, §4.6). Otherwise it is "unverified".
4. **Re-baseline** after 2 s of continuous rejection while pairs keep arriving (logged).
5. **Detect freezes:** no new displayed pair for more than 125 ms → `freeze_start`; then `freeze_end` with its duration.
6. **Keep the display strictly increasing.** Superseded, incomplete, missing and rejected sequence numbers are counted by cause.

The display tick is Unity's frame rate (60 Hz or higher), not a simulated 60 Hz. The panel's refresh rate is logged and the analysis accounts for it.

### 4.5 Reconnect and shutdown

- **Per eye, a state machine:** down → connecting → up, with backoff 0.25 s doubling to 1 s. `link_up` is logged only after the **first decoded frame** on the new connection, not when the socket opens (the 04B lesson).
- **A reconnect** resets that eye's pairing state and the freshness reference, so no frame from before the outage can be shown after it (the R3 equivalent).
- **Shutdown** on Play Mode exit, `OnDisable` or application quit:
  - set the interrupt flag, join the threads with a 3 s bound, and free the FFmpeg contexts;
  - **no `Thread.Abort`** (Side Quest finding B8);
  - log `run_end` with counters.
- Editor domain reloads must find no live threads.
- `Application.runInBackground = true`, so that losing focus does not stall reception.

### 4.6 Clocks and the frame-age definition

- **Monotonic clock:** **`QueryPerformanceCounter` called directly** (P/Invoke), converted to ns.
  - **[V, compatibility milestone]** Python 3.13's `time.monotonic_ns()` is raw QPC (it matches to 0.001 ms).
  - Unity's Mono `Stopwatch.GetTimestamp()` is **not**: its frequency is a fixed 10 MHz and its epoch about 6.75 h away. Using it would have corrupted same-host frame ages.
  - With direct QPC, the Unity and Python offsets (UTC − monotonic) agree within 0.01 ms, in the Editor and in the player.
- **UTC:** `GetSystemTimePreciseAsFileTime` through P/Invoke. The precision of Mono's `DateTime.UtcNow` is not relied on [U].
- **Display time:** the monotonic and UTC time at the point in `Update()` where the chosen pair's textures have just been uploaded for the frame that first shows it. This is the same definition as the reference presenter's display tick. Photons appear later (render, vsync, compositor); that is measured separately by glass-to-glass tests (G4) and never mixed into G1/G2 numbers.
- **Each `frames.csv` row also records:** `Time.frameCount`, the Unity frame time, and the display refresh rate.

## 5. Keeping experimental logging consistent between 2D and XR

1. **One logging component** in the shared C# core, used unchanged by both builds.
   - **Records:** the COROL §9 / Task 04B event format (`event_id, session, trial, source, type, t_utc, t_utc_ns, t_mono_ns, host, payload`).
   - **Event types are the reference receiver's:** `link_up`, `link_down`, `freeze_start`, `freeze_end`, `pair_rejected`, `integrity_error`, `sei_error`, `decode_error`, `run_start`, `run_end`.
2. **The same per-run files and column names as the Python receiver:** `events.jsonl`, `frames.csv`, `arrivals.csv`, `summary.json`.
   - Then `analyse_poc.py` and `smoke_check.py` can score a Unity run against the same criteria with the same code.
   - If a column cannot be produced identically, the difference is documented and any analyser change is **versioned**, never edited in place.
3. **`run_start` records the context:** condition (`2D`/`XR`), platform, build ID, Unity version, scripting backend, graphics API, display refresh rate, XR runtime (if any), receiver parameters, FFmpeg version and licence string, and the FrameMeta version.
4. **One definition of "displayed"** in both conditions (§4.6). XR-only extras (for example OpenXR's predicted display time) are **additional** fields, never substitutes.
5. **Writing stays off the main thread:** a bounded queue and a background writer, flushed at quit. A full queue is counted, never blocking. Run folders are `unity_rx_<stamp>_<platform>_<camera>_<label>/`. On Quest, files go under `persistentDataPath` and are pulled after the session (later).
6. **Cross-host time** (later): the backend's clock-offset probes (architecture A8) are logged by the same component.

## 6. Path to Meta Quest 3 (gate G3; not part of Task 05)

| Component | Windows M1 | Quest 3 | Change |
|---|---|---|---|
| `IStereoVideoSource`, FrameMeta/SEI parser, Annex-B utilities | C# core | Same | **None** (IL2CPP-compatible C#) |
| `StereoPresenter` (pairing, freshness, freezes) | C# core | Same | **None** |
| Logging, clocks | C# core | Same; precise UTC via the Android API | Small platform shim |
| R8 texture upload, shader | C# + URP shader | Same if the decoder yields CPU luma; eye selection by `unity_StereoEyeIndex` (Single Pass Instanced) | Shader mode switch only |
| **Transport + decoder back-end** | FFmpeg (Windows DLLs, x64) via AutoGen | **Replaced** | One of: **(a)** rtsp-client-android + low-latency MediaCodec (GPU surface → external texture → blit; SEI access [U]; Vulkan external textures harder [U]); **(b)** an FFmpeg arm64 LGPL build (RTSP + `h264_mediacodec`), reusing most managed code (needs an NDK build; MediaCodec latency through FFmpeg [U]); **(c)** a shared C# RTSP/RTP client + MediaCodec through JNI in buffer mode (CPU luma copy), which keeps SEI, access-unit and frame-end handling in shared C# |
| Scripting backend | Mono for M1 | IL2CPP (required) | IL2CPP compatibility of the core checked before G3 |

The seam is a back-end interface that delivers *decoded eye frames* (metadata, luma buffer or texture, receive times) and link events. Any of (a)–(c) fits behind it. The choice is made at G3, against the Task 04A G3 criteria. If G3 fails after one fix iteration, the JPEG fallback is switched for **both** conditions together (Task 04A §7).

## 7. Milestone M1: scope, steps and acceptance criteria

**Scope:**
- Camera A only.
- Both eye paths received and paired; the left eye displayed full-screen on a quad or `RawImage`.
- An **experimenter/debug overlay** shows the right eye as a small inset, plus frame age, rate, link state, freeze count and rejections. It is not participant-facing.
- Editor Play Mode for development; **measurements in a Windows Standalone (Mono) build.**
- No XR, no AI2 UI, no backend, no Camera B, no crop, no camera hardware.

**Steps:**

| Step | What | Network / processes | Approval |
|---|---|---|---|
| T0 | Create a **new** Unity project from the URP template with 6000.3.28f1 (§8). Download and verify FFmpeg.AutoGen 9.0.1.1 (nuget.org) and BtbN FFmpeg n9.0 `win64-lgpl-shared` (SHA-256 against the release's `checksums.sha256`). Confirm AutoGen loads under Unity Mono (netstandard2.1) [U] and the licence string is LGPL | Downloads only | **Yes** (installs) |
| T1 | Offline EditMode tests (Unity Test Framework): FrameMeta and SEI against golden vectors generated by `poc_common` (incl. CRC and emulation-prevention cases); Annex-B splitting; presenter scenarios ported from `tests/test_freshness.py` (stall, burst backlog, obsolete discard, rebaseline, reconnect reset, strict ordering) | None | Covered by T0 |
| T2 | **Offline file replay.** A recorded camera-A stream (left and right `.ts` files with SEI and frame-end) is generated with the existing publisher code writing to files (no server). The Unity file-input mode then decodes it in Play Mode at real-time pace. Checks: decode, SEI, barcode, PSNR, texture path, frame-time cost, the monotonic-clock agreement (§4.6) and clean shutdown | None | Covered by T0 |
| T3 | **Live localhost smoke, 60 s, no faults.** MediaMTX (verified localhost config) + `publish_synthetic.py --camera A --frame-end sei` + the Unity Standalone receiver, **plus the Python reference receiver reading the same paths in parallel** (MediaMTX fans out), so Unity and Python are compared on the identical stream | Localhost RTSP only | **Yes** (separately) |
| T4 | **Live fault run, about 6 min.** The G1 faults compressed: 300 ms burst stall at 60 s, 700 ms burst at 120 s, 700 ms drop at 180 s, 5-frame drop at 240 s, MediaMTX restart at 300 s (down 5 s). Unity and Python receivers in parallel; keep-awake and cleanup as in the G1 rerun | Localhost RTSP only | **Yes** (separately) |

**M1 acceptance criteria (Task 05 M1 criteria v1; scored on T4, camera A, Unity receiver).** The researcher reviewed these on 5 Nov, and the **numerical thresholds are retained exactly as below**. Any change needs review and a new criteria version. M1.4 uses **S7b v2** (adopted for future tests, decision 8).

| # | Criterion | Origin |
|---|---|---|
| M1.1 | Continuous decode and display over the run; 0 decoder errors after sync | G1.2 |
| M1.2 | 100 % of displayed pairs have equal L/R sequence numbers; 0 integrity errors (SEI against barcode) | G1.1 |
| M1.3 | Capture → display age (same-host clock), outside fault windows: median ≤ 60 ms, p95 ≤ 100 ms. **Also reported:** the difference from the parallel Python receiver | G1.3 |
| M1.4 | After each burst stall, ≤ 2 frames to recover and ≤ 2 burst frames shown; no stale pair displayed (**S7b v2**) | G1.4, S7b v2 |
| M1.5 | Every stall logged as a freeze; missing count ≥ the injected count and explained | G1.5 |
| M1.6 | Display resumes ≤ 3 s after the publisher reconnects; no pair captured before the stop shown after it | G1.6, R3 |
| M1.7 | 0 SEI CRC errors and 0 frames without SEI | G1.7 |
| M1.8 | Decoding off the main thread; Unity frame-time p99 ≤ 1.5 × the display period during decoding | G2 |
| M1.9 | Displayed left image against the source: PSNR ≥ 40 dB on sampled frames | G2 |
| M1.10 | Clean shutdown: threads joined and sockets closed ≤ 3 s after quit; no orphan process; port 8554 closed after MediaMTX stops | S8 lesson |

**Deferred to complete G2 (after M1):** Camera B and source switching; the exact Camera A UV crop check; the 60-minute memory-growth run; the same tests as a full 11-minute plan.

## 8. Project set-up and boundaries

- **New project (created 5 Nov):** `Phase2_Interface\unity\Phase2Client`, 6000.3.28f1, URP 17.3.0, linear colour space. This is the single Phase 2 codebase (D4).
  - **Deviation:** the Hub's Universal 3D template package (`urp-blank@17.0.14`) is not available offline or in the package registry. The project was created with the Editor's `-createProject` and configured to URP by `ProjectSetup.ConfigureUrp`, using the same URP, Test Framework and uGUI versions the template gave `My project`.
  - **Version control:** a local Git repository, no remote, nothing committed yet. Binaries, builds, `Library` and `test_results/` are ignored.
  - **Assemblies:**
    - `Phase2.Video.Core`: no Unity rendering dependencies, no `unsafe`;
    - `Phase2.Video.Ffmpeg`: Windows-only, `allowUnsafeCode`, AutoGen and DLLs under `Plugins/x86_64`;
    - `Phase2.Video.Unity`: MonoBehaviours, shader, overlay;
    - `Phase2.Video.Tests`: EditMode.
  - **Scene:** `Task05_WindowsReception`.
- **Configuration:** a JSON file in the run folder (server URL, camera, receiver parameters, output folder). The URL guard is ported from `poc_common.check_local_url`: loopback only, never ports 8080/8081.
- **Not touched:** `My project`, the recovered Side Quest project and repositories, `camera_validation/`, COROL, the Task 04B code and evidence (the publisher and MediaMTX are used as they are).

## 9. Risks

| Risk | Mitigation |
|---|---|
| FFmpeg.AutoGen 9.0.x does not load under Unity Mono, or its struct layouts mismatch the DLL build [U] | Check in T0: pin matching versions and check `avcodec_version()` at startup. Fallback: hand-written minimal P/Invoke, or the C++ plugin (toolchain approval) |
| Main-thread upload or GC spikes inflate frame age | Pooled buffers, no per-frame allocations; measure in the Standalone build (M1.8); native upload later if needed |
| Unexpected parser holdback (a sender without frame-end) | Frame-end presence logged; publisher always `--frame-end sei`; requirement passed to the gateway (Task 04) |
| The ~300 ms delays recur during T3/T4 | The parallel Python receiver separates transport effects from Unity effects |
| The laptop panel's refresh rate (possibly above 60 Hz) changes the display-tick quantisation | Refresh rate logged; analysis uses the actual tick |
| Windows Defender/SmartScreen on the first launch of an unsigned Unity build | Stop and report, as with MediaMTX. Outbound loopback only, so no inbound firewall rule should be needed [I] |
| Editor-specific stalls (domain reload, Editor GC) | Development only; criteria scored on the Standalone build |

## 10. Decisions (researcher, 5 Nov 2026)

| # | Decision |
|---|---|
| 1 | New project at `unity\Phase2Client`, Unity 6000.3.28f1, URP. `My project` untouched |
| 2 | Separate local Git repository with Unity and test-results exclusions. No remote; downloaded binaries never committed |
| 3 | M1 scope: camera A synthetic stereo; both eyes received and paired by frame number; left eye displayed; right-eye debug view, frame age, link status and logging |
| 4 | Investigate FFmpeg.AutoGen 9.0.1.1 with BtbN's Windows x64 FFmpeg 9.0 LGPL shared build; verify versions, provenance, checksums, licensing and binary compatibility before use |
| 5 | Check Unity 6.3, the managed backend, native DLL loading, `unsafe` C# and the required exports. Do not assume the PyAV FFmpeg version |
| 6 | Minimal decoder compatibility test first; if unsuitable, stop and report alternatives |
| 7 | Reuse the Python receiver's log schema and events; Unity runs go under `Phase2Client/test_results` (git-ignored) |
| 8 | **S7b v2 adopted for future tests only;** the S7b v1 historical FAIL is preserved |
| 9 | Freshness indicators only in a developer debug overlay; no participant-interface decisions yet |
| 10 | The ten M1 criteria are retained with their exact thresholds (§7). No live tests or threshold changes without review |
| 11 | Future comparisons run the Python reference receiver alongside Unity on the same stream. Unity is started manually at first |
| 12 | University licensing review before external distribution. FFmpeg binaries are isolated and replaceable |

**Still open (for later approval):**
- the live tests T3 and T4;
- whether a later orchestrator option launches Unity automatically;
- a participant-facing stale or no-signal indicator (research design).

## 11. Sources (accessed 5 Nov 2026)

- FFmpeg.AutoGen: [repository](https://github.com/Ruslan-B/FFmpeg.AutoGen) (MIT licence, changed from LGPL) and [NuGet](https://www.nuget.org/packages/FFmpeg.AutoGen) (9.0.1.1, 16 Aug 2026; netstandard2.0/2.1, net8.0).
- BtbN FFmpeg-Builds: [repository](https://github.com/BtbN/FFmpeg-Builds) and [latest release](https://github.com/BtbN/FFmpeg-Builds/releases/tag/latest) (`win64-lgpl-shared` variants pinned to 9.0 and 8.1; `checksums.sha256`).
- Videolabs (vendor of VLC for Unity; treat as a vendor claim): [RTSP in Unity guide](https://videolabs.io/unity-video-guides/rtsp-player/) and [plugin comparison](https://videolabs.io/compare/).
- Vizario H264RTSP Player: [Unity Asset Store](https://assetstore.unity.com/packages/tools/video/vizario-h264rtsp-player-222837) (not evaluated).
- Local evidence: `streaming_poc/` (Task 04B), the Side Quest audit, the Task 04A audit and the COROL addendum (links above).

## 12. Compatibility milestone results (5 Nov 2026; offline synthetic input only)

**Run conditions:**
- No MediaMTX, no streaming, no cameras or robots.
- **Input:** camera A, 120 frames per eye, encoded by the Task 04B publisher code (imported read-only) into MPEG-TS files, with the FrameMeta SEI and end-of-frame SEI (`Tools/make_synthetic_input.py`).
- **Evidence:** `unity/Phase2Client/test_results/` (git-ignored); summary in `test_results/compat/COMPAT_RESULTS.md`.

| Check | Editor (EditMode, Mono, D3D12) | Windows standalone player (Mono, x64, D3D12) |
|---|---|---|
| Downloads | AutoGen SHA-512 matches the NuGet catalog; NuGet repository signature valid. FFmpeg SHA-256 matches `checksums.sha256` and the pinned digest | (same files) |
| Static DLL check (`pe_exports.py`) | x64; 37/37 required exports; all imports resolve | — |
| C01 runtime, version, licence | PASS: `n9.0.2-39-g7adfbe40dc-20261031`, avcodec 63.1.102, **LGPL version 3 or later**; modules loaded from the project's plugin folder | PASS: loaded from `Phase2CompatProbe_Data\Plugins\x86_64` |
| C02 required exports at runtime | PASS 37/37 | PASS 37/37 |
| C03 decode + metadata (each eye) | PASS: 120/120 frames, native `h264` decoder, yuv420p 1280 × 800; 0 decode errors; 0 CRC errors; all fields equal the manifest; frame-end placement correct | PASS (same) |
| C04 image (PSNR against the source luma) | PASS: min 62.9 / 63.0 dB (threshold 40) | PASS (same) |
| C05 pairing by frame number | PASS: 120 complete pairs, 0 unmatched | PASS |
| C06 both eyes on two background threads | PASS: 240 frames in 175 ms | PASS (267 ms) |
| Packet → decoded frame, median / p95 / max | 0.53 / 3.0 / 20.1 ms | 1.43 / 2.4 / 6.8 ms |
| C07 interrupt stops a blocking read | PASS: `AVERROR_EXIT` after 1 ms | PASS |
| C08 R8 texture upload, GPU round trip | PASS: max diff 0 over 29,440 pixels; upload 1.3 ms | PASS (0.5 ms) |
| C09 monotonic clock = Python's QPC | PASS after the fix (offset difference 0.00 ms). **First run FAILED** with Mono `Stopwatch` (6.75 h epoch difference) | PASS |
| `unsafe` C#, precompiled AutoGen under Unity Mono (netstandard2.1) | Compiles and runs | Built (Mono2x) and runs |

**Failures found and handled (no large workaround):**
1. **Clock source.** Mono's `Stopwatch` is not QPC, so `Clocks.MonoNs` now calls `QueryPerformanceCounter` directly (§4.6).
2. **Frame-end expectation.** The test initially expected each frame's own marker in its packet; corrected to the actual placement (§4.1). The decoder now also records markers in slice-less packets.
3. **Test assembly definition.** It referenced the test runner twice; fixed.

**Not yet covered (belongs to M1):**
- RTSP input;
- reconnect;
- the presenter and freshness logic in C#;
- the display scene and debug overlay;
- the log-schema writer;
- IL2CPP.

**Verdict:** the FFmpeg.AutoGen + BtbN FFmpeg 9.0 LGPL route is **suitable**. Implementation of the full M1 receiver can proceed, offline steps first; T3 and T4 need separate approval.

## 13. M1 offline implementation (5 Nov 2026; approved; offline only)

**Built in `unity/Phase2Client`.** The validated FFmpeg dependencies are unchanged.

| Part | Where | Notes |
|---|---|---|
| FrameMeta, SEI, clocks (QPC), barcode, URL guard, backoff, host ID | `Phase2.Video.Core` | Pure C#, no FFmpeg, no rendering |
| **StereoPresenter**: a statement-by-statement port of `receive_reference.Presenter` | `Phase2.Video.Core` | Pairing by verified seq, newest complete pair, excess-delay rejection of the pair and the obsolete backlog, strictly increasing display (never fast-forwards through stale frames), separate absolute and relative measures with labels, re-baseline, reset on reconnect |
| ReceiverCore, LumaStore (bounded, 24 per eye, pooled), logs | `Phase2.Video.Core` | `events.jsonl`, `frames.csv`, `arrivals.csv`, `summary.json` in the Python schema, written off the main thread; plus `ticks.csv` and `ops.csv` (presenter inputs in lock order, for oracle replay) |
| **Backend seam:** `IStereoBackend` with a name registry | `Phase2.Video.Core` | The Unity layer never references FFmpeg; a Quest backend registers under its own name |
| FFmpeg backend: two reader/decoder threads | `Phase2.Video.Ffmpeg` | Port of `EyeReader`: RTSP/TCP with the reference options, reconnect 0.25 s doubling to 1 s, interrupt-based stop. File replay follows a recorded schedule; a segment end is a link loss and reconnect |
| Unity receiver, display rig, overlay, shader | `Phase2.Video.Unity` | Left eye on a quad with the Camera A crop (x 39–1276, y 6–775); developer-only right-eye inset and overlay (F1/F2); one minimal unlit shader (R8 → grey, row flip, crop, sRGB→linear) |
| Scene and player | `Assets/Phase2/Scenes/M1_WindowsReception.unity`; `M1Build.BuildPlayer` → `Builds/M1/Phase2M1.exe` | Command-line `-m1Mode file_replay\|rtsp`, `-m1Replay`, `-m1Server`, `-m1Seconds`, `-m1Label`, `-m1Out`, `-m1Quit` |

**Deviations from this plan, as built:**
- **link_up:** follows the Python reference (logged when the input opens, then the presenter resets), not "after the first decoded frame" (§4.5). This keeps the event definitions identical. For RTSP *input*, opening already means the server has answered.
- **File replay never trusts the clock** (absolute age reported unavailable), because the recorded capture stamps come from the recording session.

**Offline verification (all PASS; evidence in `unity/Phase2Client/test_results/`, summary `m1/M1_OFFLINE_RESULTS.md`):**
1. **Differential tests:** the C# presenter against the Python oracle on 20 traces: 16 scripted Task 04B scenarios and 4 recorded-run replays (smoke 1 holdback with the safeguard on and off; G1 rerun cameras A and B, with real stalls, drops and the restart). **0 mismatches** over about 79,000 ticks.
2. **Core and backend tests:** core unit tests, plus the FFmpeg backend over a recorded two-segment scenario (decode, metadata, eye identity, picture = metadata, reconnect). EditMode total 30/30.
3. **Full receiver on the recorded scenario** in real time, in Editor Play Mode and in the standalone player. Each run's own logs are verified by `Tools/verify_unity_run.py`:
   - the oracle replay of Unity's presenter inputs matches exactly;
   - all 11 scenario checks pass: integrity, pairing, order, burst stall not fast-forwarded, drops counted, reconnect without stale replay, freezes, clock measures distinguished, image, clean run, and an S7b v2 offline analogue.
4. **Rendering:** pixel-exact against the uploaded luma over the full crop (max diff 0) on D3D12; displayed frames at least 62.9 dB PSNR against the source.
5. **Player timing (indicative):** frame interval p99 17.44 ms at 60 Hz; upload 0.34 ms median; decode 1.2 ms median off the main thread.

**Still untested:**
- RTSP from MediaMTX in Unity;
- live reconnect against a server;
- same-host absolute age;
- Defender or firewall behaviour for the Unity executable;
- the existing analysers on a Unity folder;
- the M1 criteria;
- IL2CPP and Quest.

**T3 (60 s Unity smoke) readiness:** technically ready, pending approval. See the checkpoint §13.12 for the proposed procedure and the open decision on how to launch it.

## 14. T3: first live Unity RTSP smoke test (5 Nov 2026, approved)

Results: `unity/Phase2Client/test_results/m1_smoke_20261105_170126/M1_SMOKE_RESULTS.md`.

**Set-up:**
- orchestrator v2 with `-Cameras A -NoRestart -Seconds 100 -ExternalProcess Phase2M1`;
- the Unity player started by hand with `-m1Mode rtsp -m1Seconds 75`;
- the Python reference receiver on the same streams.

**Result: PASS for everything the smoke can test:**
- **Decoding:** live RTSP decoding of both eyes (1,475 frames per eye, 0 decode or SEI errors).
- **Pairing:** 1,464 displayed pairs, all eye- and seq-correct.
- **Metadata:** identical to the publisher's record.
- **Image:**
  - the displayed frames match the source exactly as well as Python's do (68–73 dB, identical values);
  - the left-eye render is pixel-exact.
- **Freshness:** same-host absolute age trusted. Capture → display median 27.8 ms, p95 39.3 ms (Python 39.0 / 39.9).
- **Oracle replay** of Unity's live presenter inputs: exact.
- **Clean shutdown and cleanup;** no security events.

The M1 criteria are not scored (T4).

**Changes needed before T4:**
1. **An M1 scorer** implementing M1.1–M1.10 with the retained thresholds, reading the Unity, publisher and orchestrator evidence.
2. **S7b v2** implemented as its own key in `smoke_check.py`.
3. **Unity resource sampling:** extend `-ExternalProcess` to sample the player's CPU and memory.
4. **The cosmetic `cleanup.json` fix** (`{}` → `[]`).
5. **A right-eye inset check:** a pixel check of the inset or a screenshot (optional).
6. **Start-up:** consider disabling the default splash screen (if the licence allows), or start Unity before the measurement window. About 8 s from launch to first frame.
7. **The T4 plan:** orchestrator `-Cameras A` with the restart enabled and faults on the compressed schedule; the publisher must outlast the Unity session.

## 15. T4 preparation: six-minute fault-injection validation (5 Nov 2026; prepared, NOT run)

### 15.1 Changes made (all offline-tested)

| Change | Where | Test |
|---|---|---|
| **M1 scorer:** M1.1–M1.10 with the retained thresholds. It reuses the G1 analyser's fault windows and recovery rule and `smoke_check`'s S7b v2. A run is **formal M1 evidence only in the T4 configuration**, so the T3 smoke scores "NOT FORMAL" | `unity/Phase2Client/Tools/score_m1.py` | `Tools/test_score_m1.py`, 49/49: every criterion at its threshold boundary, plus T3 integration (NOT FORMAL, evidence unchanged) |
| **S7b v2:** a separate key `S7b_v2_stale_frame_rejection`; v1 code and all historical verdicts unchanged | `streaming_poc/smoke_check.py` (`s7b_v2`) | `tests/test_s7b_v2.py`, 15/15 (synthetic edges; G1 rerun's v1 recomputes identically to its recorded FAIL; evidence unchanged) |
| **Orchestrator v3:** `-ExternalProcess` finds the hand-started player by name, samples its CPU and memory (`resources.csv` role `ext_Phase2M1`) and records its start and exit time and exit code. Cleanup's empty list is now `[]` (T3's `{}` reproduced, then fixed). Cleanup behaviour unchanged | `streaming_poc/run_smoke_restart.ps1` | `-SelfTest` PASS; `tests/test_orchestrator_plans.py` 13/13: default plan = G1 rerun arguments, T3 plan = T3 arguments, T4 plan, bad `-Cameras` refused |
| **Unity instrumentation only:** shutdown timing (`summary.unity.shutdown`); per-frame render-submission time (`ticks.csv render_end_mono_ns`); **right-eye developer display check** (the actual right-eye quad, material and texture rendered 1:1 against the decoded right frame) | `Phase2.Video.Unity` | EditMode 30/30; Play Mode 1/1 (asserts both eye checks); rebuilt player replay: oracle PASS, **left and right pixel-exact (max diff 0)**, readers joined 1.9 ms after quit |
| Verifier: the right-eye check is included | `Tools/verify_unity_run.py` | the replay run above |
| Unity splash and start-up: **unchanged**; covered by the schedule | — | — |

### 15.2 Frame-age definitions (Python and Unity)

| Stage | Field | Python receiver | Unity receiver |
|---|---|---|---|
| Capture | SEI `t_host_mono_ns` / `t_utc_ns` | publisher, before encode | same SEI |
| Send | publisher `sent.csv t_sent_mono_ns` | its RTSP write returned | same |
| Receipt | `arrivals.csv t_arrival_mono_ns` | the demuxer returned the packet (after FFmpeg's parser) | same definition (FFmpeg 9.0 demuxer, reader thread) |
| Decode complete | `t_decoded_mono_ns` | decoder returned the picture | same |
| Pair complete | `frames.csv delay_ms` (UTC) | later eye's receipt − capture | same |
| **Selected / displayed** | `frames.csv t_display_*`; **the M1.3 / G1.3 age** | a **simulated** 60 Hz tick; nothing is rendered | the start of the Update() that selects the pair (real vsync frame) |
| Texture upload | `ticks.csv upload_ms` | — | after selection, both eyes |
| Render submitted (CPU) | `ticks.csv render_end_mono_ns` | — | URP finished submitting that frame |
| GPU done / flip / photons | — | **not measured** | **not measured.** No physical display latency is claimed; that needs glass-to-glass instrumentation (G4) |

**T3 Unity breakdown (median / p95, ms):**

| Stage | Median | p95 |
|---|---|---|
| Capture → send | 14.4 | 22.0 |
| Send → receipt | 2.7 | 6.0 |
| Receipt → decode | 1.6 | 2.6 |
| Pair decoded → selected | 7.1 | 15.5 |
| Capture → selected | 27.8 | 39.3 |

**Offline replay (Unity):** tick → render submission median 1.3 ms.

**Observation:** the Python receiver's capture → selected median depends on the window: 23.1 ms over its whole T3 run, 39.0 ms over the window shared with Unity. This is consistent with its simulated tick beating against 20 fps (not investigated further).

### 15.3 Exact T4 schedule (t = 0 at publisher start)

| t (s) | Event |
|---|---|
| −7 … −1 | Orchestrator v3: preflight (8554 free, verified config SHA-256), MediaMTX launch, listener check (127.0.0.1:8554 only); keep-awake held |
| 0 | Publisher A starts: synthetic stereo, 20 fps, H.264 Constrained Baseline, 8 Mbit/s per eye, `--frame-end sei`, 400 s |
| 1.5 | Python reference receiver A starts (freshness safeguard defaults, raw probe, frames saved every 200) |
| about 3 | **Operator launches the Unity player** as soon as the orchestrator logs "receivers started" (scripted wait, as in T3) |
| about 11 | Unity's first displayed frame (T3: 8.0 s after launch, splash unchanged) |
| **20** | **Measurement window W opens** (9 s after the expected first frame) |
| 60 | 300 ms burst stall |
| 120 | 700 ms burst stall |
| 180 | 700 ms drop stall |
| 240 | 5-frame drop |
| 300 | MediaMTX stopped (scheduled clock) |
| 305 | MediaMTX restarted; publisher, Python and Unity reconnect |
| **380** | **Measurement window W closes** (W = 360 s) |
| about 389 | Unity session ends (`-m1Seconds 380` from its Start(), about t 9 s); player quits |
| 400 | Publisher ends; done flag |
| about 403 | Python receiver ends (done flag + 3 s drain) |
| about 403–410 | Orchestrator: Python and Unity exit waits (≤ 60 s each), MediaMTX stop, cleanup check, keep-awake release |

**Margins:**
- W opens 9 s after Unity's expected first frame.
- Unity ends 9 s after W closes.
- The publisher and server outlive Unity by about 11 s.
- **If Unity's first frame comes later than t = 20 s, M1.1 fails as recorded.** The window is not moved after the fact.

**Commands (from `streaming_poc` and `unity/Phase2Client`):**
```powershell
powershell -ExecutionPolicy Bypass -File .\run_smoke_restart.ps1 -Cameras A -Seconds 400 -Stall 60:300:burst,120:700:burst,180:700:drop -Drop 240:5 -RestartAt 300 -DownSeconds 5 -Label m1t4 -ExternalProcess Phase2M1 -ExitWaitSeconds 60
# on "receivers started":
Builds\M1\Phase2M1.exe -m1Mode rtsp -m1Server rtsp://127.0.0.1:8554 -m1Seconds 380 -m1Label t4 -m1Quit -m1Out test_results\m1_t4_<stamp> -m1SaveEvery 200 -logFile test_results\m1_t4_<stamp>\unity_player.log -screen-fullscreen 0 -screen-width 1280 -screen-height 800
```

**Analysis:**
- `verify_unity_run.py` (oracle replay);
- `score_m1.py --window-start-s 20 --window-end-s 380 --python-rx …` (**the formal M1 verdicts**);
- `compare_unity_python.py`;
- `smoke_check.py` on the Python side (with S7b v1 and v2);
- a read-only Defender, AppLocker, Firewall and power log query.

All evidence goes in new folders.

### 15.4 Criteria to be scored (v1, thresholds unchanged)

| # | Criterion (as approved) | How `score_m1.py` scores it |
|---|---|---|
| M1.1 | Continuous decode and display over the run; 0 decoder errors after sync | Unity display spans W (first ≤ 20 s, last ≥ 380 s); 0 decode errors after sync |
| M1.2 | 100 % displayed pairs equal L/R seq; 0 integrity errors | every displayed pair `eye_ok` and `barcode_ok`; presenter integrity errors 0 |
| M1.3 | Capture → display age outside fault windows: median ≤ 60, p95 ≤ 100 ms; Python reported | Selecting tick − capture (max of both eyes, same host), within W, excluding the G1 analyser's fault windows: stall + 1 s, drop/link events + 3 s, Unity link_down + 3 s. Python on the same windows |
| M1.4 | Each burst stall: ≤ 2 frames to recover, ≤ 2 burst frames shown; S7b v2 | G1 recovery rule (age ≤ clean median + 20 ms) for the 60 s and 120 s bursts; burst displayed ≤ 2; S7b v2 PASS on the Unity run |
| M1.5 | Every stall logged as a freeze; missing ≥ injected and explained | Unity freeze_start per stall in W; presenter missing ≥ injected (14 drop-stall + 5 dropped, if in range); every missing seq is either never sent by the publisher or sent while Unity's link was down |
| M1.6 | Display resumes ≤ 3 s after the publisher reconnect; no pre-stop pair shown after | first Unity display ≥ the publisher's reconnect link_up, ≤ 3.0 s later; no displayed pair after the stop with a capture before it |
| M1.7 | 0 SEI CRC errors, 0 frames without SEI | reader counters and arrivals |
| M1.8 | Decoding off the main thread; frame-time p99 ≤ 1.5 × display period | backend reader threads (by construction); `ticks.csv` frame interval p99 within W ≤ 1.5 × 1000/refresh (24.96 ms at 60.1 Hz) |
| M1.9 | Displayed left image against the source PSNR ≥ 40 dB | left render check max diff ≤ 2, and every saved left frame (every 200th) ≥ 40 dB against the regenerated source |
| M1.10 | Clean shutdown ≤ 3 s; no orphans; 8554 closed | readers joined ≤ 3 s after quit; player exit ≤ 3 s after quit (orchestrator v3 exit time); no test Python or player left; MediaMTX stopped; 8554 not listening |

**Formal evidence requires:**
- camera A only;
- the restart enabled and inside W;
- burst and drop stalls and a frame drop;
- Unity in rtsp mode.

**Overall:** PASS only if all ten pass; otherwise FAIL or INCOMPLETE.

### 15.5 Readiness

- **Prepared and offline-tested.** **Not run.** The live T4 needs separate approval.
- **Residual risks:**
  - Unity start-up slower than about 17 s after launch (M1.1);
  - the intermittent ~300 ms localhost delays from G1 (would show in M1.3 and M1.8, and are compared with Python);
  - Unity's live reconnect, untested until T4.

## 16. T4 result (5 Nov 2026, 17:35)

**Formal M1 evidence; result FAIL** (M1.4, M1.5, M1.6). Details: `unity/Phase2Client/test_results/m1_t4_20261105_173459/T4_RESULTS.md` and checkpoint §13.15.

The failures trace to:
- the S7b v2 definition;
- the ~300 ms transport delays overlapping the 120 s stall;
- a scorer deviation from R3's 200 ms grace.

They do not trace to receiver behaviour: the oracle replay is exact, and the Python reference behaves the same way.

## 17. M1 scoring corrections and supplementary re-score (6 Nov 2026; offline, approved)

Details: `unity/Phase2Client/test_results/m1_t4_rescore_v2_20261106/RESCORE_RESULTS.md` and checkpoint §13.16. **Erratum to §16:** "the Python reference behaves the same way" does not hold for burst recovery. Python took 0 frames and Unity 1–2, because Unity showed post-burst frames sooner; see the erratum in `T4_RESULTS.md`.

### 17.1 Versions (numeric thresholds identical throughout)

| Version | What | Status |
|---|---|---|
| Scorer 1.0 | Produced the recorded T4 verdicts | Kept only for reproduction (`--scorer-version 1.0 --criteria v1`) |
| Scorer 1.1 | M1.6 applies R3's existing 200 ms in-flight grace (conformance fix) | Default |
| Criteria v1 | §7 / §15.4 as approved on 5 Nov | Recorded T4 result |
| **Criteria v2 (POST-HOC)** | **M1.4:** S7b v3 (no duplicate 0-frame recovery rule; pre-stall frame held only if send→receipt > 50 ms). **M1.5:** freeze onset in [start − 200 ms, end + 500 ms], or an earlier freeze still active at the stall end (the condition, onset and duration are recorded). **Non-gating:** unscheduled freezes (count, median, maximum) | Default for future runs |

### 17.2 T4 verdicts

- **Original (v1, scorer 1.0): FAIL.** This is the recorded result, reproduced exactly.
- **Supplementary (v2, scorer 1.1, post-hoc): PASS 10/10.**
- **Genuine performance issue, unresolved:** 93 unscheduled freezes in 360 s (median 382 ms) in both receivers, and 287 publisher discards while connected.

### 17.3 Readiness for a first real Camera A preview in Unity (assessment only; nothing started)

**Ready:**
- **The receiver chain:** RTSP/TCP, the H.264 decoder threads, SEI pairing and the freshness presenter. It is oracle-exact, reconnects in under 2 s and shuts down cleanly.
- **The scoring tools:** they carry explicit versions.

**Must be built before a live preview (each offline-testable; installs need approval):**
1. **A real Camera A gateway publisher. This does not exist yet.** It would take the OAK `VideoEncoder` H.264 output for both eyes, insert the FrameMeta SEI and the frame-end SEI host-side (`poc_common.insert_sei_before_vcl` and `append_frame_end` work on Annex-B), and send it to MediaMTX through the existing PyAV mux path.
   - It needs DepthAI and PyAV in one environment, or a pipe between the two venvs. That is a package decision needing approval.
   - It must set `AutoCalibrationMode.OFF` and confirm it with the getter, and must not change firmware, IPs or the IR emitters.
2. **A Unity source mode (synthetic or camera).** The presenter's integrity check requires the synthetic barcode, so every real pair would count as an `integrity_error`. In camera mode the barcode check must be "not applicable", while the SEI seq, eye and camera checks stay.
3. **Camera A crop.** The Unity UV crop exists but is set to the full frame. Apply the approved x 39–1276 / y 6–775.
   - **Erratum (6 Nov 2026, Task 06):** the crop was already applied (see the erratum in §4.3). Nothing needed changing; it is reconciled in the Task 06 plan §4.1.

**Known limits for the first preview (to state, not to fix):**
- **Source-based checks do not apply to a real scene:** M1.9's PSNR against the source and M1.2's barcode both need the synthetic source.
- **The capture time changes:** it becomes the device timestamp mapped to the host clock, so ages are not directly comparable with the synthetic M1.3.
- **Real camera stalls:** delivery stalls of about 2.7 per minute (Stage D, cause unknown) will appear as freezes. Separate them from transport delays by comparing the device-timestamp gaps with the send and receipt gaps; the unscheduled-freeze measure records them.
- **Isolated Ethernet:** the camera runs offline from Claude Code, so use a detached, logged runner, as with T4.

**Suggested first step:** build items 1–3 offline, then run one short approved Camera A preview (about 60 s, Camera A only, localhost MediaMTX). There is no formal pass/fail; it collects logs, the non-gating freeze measure and a visual check.

## 18. M1 closure (researcher decision, 6 Nov 2026)

**Task 05 M1: CONDITIONALLY VALIDATED.**

| Item | Result |
|---|---|
| Original T4, criteria v1 | **FAIL, 7/10** (the recorded result; unchanged) |
| Supplementary post-hoc T4, criteria v2 | **PASS, 10/10** |
| Receiver correctness | Supported |
| Unscheduled freezes outside the faults | **Unresolved performance issue** (the ~300 ms transport delays) |

**Follow-on:** Task 06, the real Camera A preview, is prepared offline. See [Phase2_Task06_CameraA_Unity_Preview_Plan.md](Phase2_Task06_CameraA_Unity_Preview_Plan.md). It adds the Unity `-m1Source camera` mode; the synthetic validation mode is unchanged.
