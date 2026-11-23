# Request: temporary Windows event-tracing rights for a short local network diagnostic

**Status:** DRAFT, not sent. To be sent by the researcher after approval.
**Prepared:** 13 November 2026.
**Requester:** [researcher name and contact], [school / project].
**Device:** [asset tag], Windows 11 Enterprise (build 26200), standard user account.

## What is needed

The minimum rights to record built-in Windows Event Tracing (ETW) for about 10 minutes, in order of preference:

1. **Preferred (least privilege):** temporary membership of the built-in **Performance Log Users** group (S-1-5-32-559) for the requester's account. Microsoft documents that this group may control event-tracing sessions. It takes effect after the user signs out and back in.
2. **Fallback, if the Microsoft-Windows-TCPIP provider refuses Performance Log Users:** a one-off elevated (Administrator) PowerShell session, or an IT staff member running the two commands below at the device.

**Duration:** one window of about 30 minutes, including sign-in and set-up; tracing itself lasts about 10 minutes. Rights are removed afterwards.

## What will be run (built-in tools only; nothing installed)

- `logman create trace … -ets` and `logman stop … -ets` start and stop a bounded trace of two built-in providers: **Microsoft-Windows-TCPIP** and **Microsoft-Windows-Winsock-AFD**. Capture is limited to 400 s and a 512 MB circular file.
- `tracerpt` decodes the trace to a local file.
- These are wrapped in a project script, `capture_o1_loopback_etw.ps1`. It prints its exact commands in plan-only mode and refuses to run unless:
  - the account has tracing rights; and
  - the laptop is disconnected from external networks (Wi-Fi off).

**Not done:**
- no software installed;
- no packet-capture driver;
- no firewall, security, network-adapter or policy setting changed;
- no remote access.

## Scope and data

- **Purpose:** to diagnose short (≈ 0.3 s) stalls on a *local* connection between two of our programs on the same laptop (127.0.0.1, port 8554). This is part of a camera-streaming research prototype.
- **During tracing:** the laptop is off Wi-Fi and university networks. The only other connection is a direct Ethernet link to a lab camera.
- **What the trace contains:** the providers are system-wide, so it may contain metadata (for example local addresses, ports, sizes and process ids) of other local connections on the laptop. No packet contents are requested.
- **What is analysed:** only the 127.0.0.1:8554 connections are kept for analysis.

## Storage and cleanup

- **Storage:** trace files stay on the laptop's local disk, in the project folder (`camera_gateway\results\o1_etw_*\raw\`), with SHA-256 hashes. They are not uploaded, synced or shared.
- **Deletion:** the raw trace is deleted once the filtered results have been extracted and validated, or earlier on IT's request. Only the filtered 127.0.0.1:8554 results are kept.
- **After the session:** the elevated window is closed and the tracing session confirmed stopped (`logman query -ets` shows no session named `Phase2_O1_Loopback`). The group membership or elevation can then be removed.

[Researcher to add: supervisor approval and any ethics or data-handling reference IT requires.]
