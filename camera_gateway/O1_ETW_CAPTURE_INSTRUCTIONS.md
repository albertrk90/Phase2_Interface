# O1 connection-specific ETW capture: instructions

**Status:** prepared and revised 13 Nov 2026. **Parked**: not run.
- **Prerequisites:** IT-granted temporary elevation and the researcher's approval.
- **Tool:** `tools/capture_o1_loopback_etw.ps1`.
- **Records:** project checkpoint §13.36–§13.37.
- **IT request:** `docs/coordination/IT_request_temporary_elevation_O1_capture.md`.

## Elevation (updated 13 Nov 2026)

The researcher has **university-approved local administrator credentials**, so the IT request is not needed to obtain elevation; it is kept only as a record.

- **How elevation happens:** through the normal Windows **UAC prompt**, in a **separate elevated PowerShell window** (`Start-Process -Verb RunAs`). The researcher types the credentials directly into the Windows prompt. They are never requested, read, stored or logged by Claude or by these scripts.
- **The online launch:** `-WaitForIsolationMinutes` lets the window be opened while still online. It then waits for Wi-Fi to be turned off and for isolation to hold for 10 s before tracing starts.
- **Authorised:** only the 10 s no-camera feasibility capture (`-Feasibility`). Its results are reviewed with the researcher before any camera capture.

## Purpose

To examine the near-constant ≈ 310 ms holds on one gateway → MediaMTX loopback connection (127.0.0.1:8554) at a time. Each hold ends with a single system-wide TCP retransmission (§13.31). The capture aims to tell apart three explanations:
- retransmission recovery;
- receiver backpressure;
- a server-side reading delay.

It can do so **only to the extent that the selected providers actually expose the needed fields**. Step 1 establishes that.

## What is collected

Built-in Windows Event Tracing (`logman`); nothing is installed.

**Collection-time filters:** an ETW provider, its keyword mask and a level. Nothing else.

| Provider | GUID | Keywords (mask) | Level |
|---|---|---|---|
| Microsoft-Windows-TCPIP | {2F07E2EE-15DB-40F1-90EF-9D7BA282188A} | `0x0000010300400104` = TcpipTcb `0x4`, Transfer `0x100`, Loopback `0x400000`, SendPath `0x100000000`, ReceivePath `0x200000000`, Dropped `0x10000000000` | 5 (verbose) |
| Microsoft-Windows-Winsock-AFD | {E53C6823-7BB8-44BB-90DC-3F86090D48A6} | `0x000000000000000E` = AFD_KW_STREAM `0x2`, SOURCE_WINSOCK `0x4`, SOURCE_TRANSPORT `0x8` | 5 (verbose) |

- **Not requested:** the TCPIP `Packet` keyword (`0x40000000000`), so no packet contents are asked for.
- **Clock:** QPC (`-ct perf`), the same counter the gateway (`time.monotonic_ns`) and Unity use. `tracerpt` renders event times in UTC; they are mapped to the gateway's clock with its recorded UTC–monotonic offset. Step 1 measures the alignment error.
- **Bounds:** circular file of at most 512 MB; at most 400 s; stopped when the runner exits.

**System-wide scope:**
- These kernel providers have **no port, address or process filter at collection** in `logman`. The raw trace therefore contains events from **other TCP connections and processes on this machine** (local services, system components).
- Isolated mode (Wi-Fi off) **reduces external traffic** but does **not** remove unrelated local metadata from the raw trace.
- Which metadata fields appear (addresses, ports, sizes, process ids, etc.) is established by step 1, not assumed.

## Post-processing (after the capture, on the decoded copy)

- **Kept for analysis:** only events of TCP 4-tuples involving **127.0.0.1:8554** (the two gateway publisher connections, MediaMTX, and the two Unity reader connections), plus AFD events of the gateway, MediaMTX and Unity process ids.
- **Excluded:** everything else, from all analysis outputs.
- **Alignment:** events are aligned with the gateway's `sent.csv` / `captured.csv` and Unity's `arrivals.csv` on the shared clock.

## Steps (in one elevated, isolated window, about 10 minutes)

1. **Preparation (normal account).**
   - Only Camera A connected; Camera B unplugged.
   - Laptop on mains.
   - Plan check: `powershell -File tools\capture_o1_loopback_etw.ps1 -Feasibility` (prints the commands; starts nothing).
2. **Isolation.** The researcher turns Wi-Fi off, as in the earlier isolated stages. This is not a policy or setting change. Claude Code is offline from here.
3. **Tracing rights** (IT-granted). Either:
   - temporary membership of **Performance Log Users** (preferred, least privilege; sign out and back in first); or
   - an elevated Administrator PowerShell, if the TCPIP provider refuses that group.

   Then `cd` to the `camera_gateway` folder.
4. **Feasibility, about 10 s, no camera:**

   ```
   powershell -ExecutionPolicy Bypass -File tools\capture_o1_loopback_etw.ps1 -Armed -Feasibility
   ```

   - It generates known local 127.0.0.1 activity (`tools/o1_etw_feasibility_traffic.py`): a timed connect marker, a data transfer, a 1 s receiver stall that fills the socket buffers, and a forced SYN retransmission.
   - `tools/analyse_o1_etw_feasibility.py` then writes `feasibility_report.json`, listing for each provider and event the **field names actually present**.
   - **Capabilities it tests:**
     - connection identity (address and port);
     - process attribution;
     - sequence and ACK numbers;
     - window information;
     - retransmission events, checked against the forced SYN retries;
     - drop reasons;
     - byte counts;
     - socket or endpoint ids;
     - timestamp alignment against the marker;
     - lost events and buffers.
5. **Camera capture, about 4 min,** only after the feasibility report exists (the script refuses otherwise):

   ```
   powershell -ExecutionPolicy Bypass -File tools\capture_o1_loopback_etw.ps1 -Armed
   ```

   This runs the unchanged default M1 preview (`run_stage2.ps1 -NetworkScope Isolated`; 120 s gateway limit, keyint 20, 150 ms, resync). If elevation is available only once, this step can wait.
6. **Close up.**
   - Close the elevated window and end the elevation (IT).
   - Turn Wi-Fi back on.
   - Analysis follows: the camera-run parser `tools/analyse_o1_etw.py` is written against the schema the feasibility report actually found.

## What could distinguish the explanations (only if step 1 verifies the fields)

| Explanation | Evidence needed (each item depends on a verified field) |
|---|---|
| Retransmission recovery | A retransmission event on the publisher connection about 300 ms after the hold onset (needs retransmission events with connection identity); ideally a drop event with a reason at the onset |
| Receiver backpressure | Advertised receive window falling to zero and recovering (needs window fields); no retransmission or drop |
| Server-side reading delay | MediaMTX socket receive completions late by about 300 ms while TCP shows no retransmission (needs AFD receive events attributed to MediaMTX's socket) |

**No packet-level ACK, receive-window or socket-read evidence is promised until step 1 shows those fields.**

## What it cannot establish

- **The cause of a loss:** why a loopback segment was lost, unless a drop event carries a reason. Linking a drop to a filter driver or security product would need WFP state and IT involvement.
- **MediaMTX internals:** its scheduling beyond its socket calls.
- **Other environments:** the inter-site network, non-loopback deployments, other machines, or the camera link.
- **Single-freeze causation,** beyond timing.
- **Completeness:** ETW may lose events under load; loss counts are reported.

## Retention (proposed local arrangement; for the researcher to confirm)

- **Retained by default:** the raw `.etl` and the decoded XML stay in `results/o1_etw_*/raw/` on this laptop's local disk, with SHA-256 hashes (`raw_sha256.txt`). They are not uploaded or synced, and stay until extraction and validation have succeeded and the researcher decides.
- **Deletion only on explicit request:** `-DeleteRawAfterValidation` deletes raw files only when validation passes. Nothing deletes the only usable evidence automatically.
- **Unrelated local metadata:** because the raw trace contains it, the researcher decides whether to delete it after validation, or to keep it under the same local storage as other study evidence.
- **Shareable outputs:** filtered analysis outputs (the 127.0.0.1:8554 connections only) are the outputs intended for sharing or backup.

## Feasibility result (13 Nov 2026, 18:39; checkpoint §13.39)

**What the selected providers actually exposed** (on known local test connections):

| Verified | Event IDs and fields |
|---|---|
| Connection identity | 1031, 1033, 1300, 1038, 1043, 1044: `Tcb`, `LocalAddress`/`RemoteAddress` (`127.0.0.1:<port>`), `Pid` |
| Per-segment send | 1332: SeqNo, SndUna, SndMax, SndWnd, RcvWnd, Cwnd, RTO, SRtt |
| Receive header | 1601: ThSeq, ThAck, ThFlags |
| Cumulative ACK | 1330: SeqNo, BytesAcked, SndWnd |
| Delivery | 1157: RcvNxt, NumBytes |
| Receiver limitation | 1626: ReceiverLimitedBytes |
| SYN retransmissions | 1186, 1351: RexmitCount, RTO |
| Drops | 1214: Reason, PacketCount, socket addresses |
| Socket calls (AFD) | 1003, 1004: enter/exit; 1000: endpoint → pid |

**Not verified:**
- data-segment retransmission (1187, 1069, 1584 seen only on an unrelated connection);
- zero window (1102 seen only on an unrelated connection);
- AFD endpoint → TCP connection mapping;
- the meaning of the numeric drop reasons.

**Decoding rules:**
- Ignore tracerpt's time-zone label (`+10:29` was shown for a `+10:30` zone; the digits are correct local time).
- Bound the Tcb → connection mapping by each connection's lifetime, because Tcb pointers are reused.

**Data handling:**
- The raw trace also contained metadata of 167 other local connections and one external connection (recorded in the rundown at session start), so raw files stay local only.

**Before any camera run:** sizing, cap and decoding (about 1 GB of trace and several GB of XML per 90 s at the current keywords).
