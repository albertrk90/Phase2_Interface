"""Ethernet-scoped network check for the live Camera A gateway (12 Nov 2026; approved by the researcher).

WHY: the validated safeguards assume the laptop is ONLY on the isolated camera network ("Wi-Fi off": every
non-loopback IPv4 address link-local). The university has since allowed Wi-Fi and wired Ethernet at the same time
(checkpoint §13.24). This module replaces the "every address link-local" pre-check, ONLY when explicitly
requested (--network-scope ethernet_scoped), with an equal-or-stronger, interface-scoped check:

  1. the camera address is link-local (169.254/16);
  2. the route the OS actually selects for the camera (Find-NetRoute) uses ONE interface X, with a Preferred
     169.254 source address on X;
  3. X is wired (not a Wi-Fi/wireless adapter), Up, carries NO non-link-local IPv4 address and NO default route,
     and has the 169.254.0.0/16 route;
  4. no OTHER connected interface offers a 169.254 route with a Preferred link-local address (the multi-interface
     duplicate-discovery situation Luxonis warns about);
  5. no other interface's subnet overlaps 169.254.0.0/16;
  6. after one unicast ping, the ARP entry for the camera on X is the recorded Camera A MAC, and no other
     interface has an entry for it.

Non-link-local addresses (e.g. university Wi-Fi) are then allowed on OTHER interfaces. The gateway in this mode does
not use DepthAI broadcast discovery at all (it would also broadcast onto the Wi-Fi network): it connects by unicast
to the camera IP and verifies device ID, IP and bootloader version before anything else, as the validated path does.

READ-ONLY: the snapshot only reads adapter, address, route and neighbour state (PowerShell Get-Net*/Find-NetRoute)
and sends one ICMP echo to the camera. It never changes any network setting.

CLI:  python -I network_scope.py --camera-ip 169.254.1.222 --camera-mac 44-A9-2C-32-3C-AC [--json out.json]
      exit 0 = scoped network OK, 2 = not OK (the problems are printed), 3 = snapshot failed.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import subprocess
import sys

CAMERA_A_IP = "169.254.1.222"
CAMERA_A_MAC = "44-A9-2C-32-3C-AC"      # recorded Camera A MAC (checkpoint §5 table; ARP on 12 Nov 2026)
LINK_LOCAL = ipaddress.ip_network("169.254.0.0/16")
WIRELESS_WORDS = ("wi-fi", "wifi", "wireless", "802.11", "wlan")
GOOD_ARP_STATES = {"reachable", "stale", "delay", "probe", "permanent"}

PS_SNAPSHOT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$cam = '{ip}'
$null = Test-Connection $cam -Count 1 -ErrorAction SilentlyContinue
$f = @(Find-NetRoute -RemoteIPAddress $cam)
$src = $f | Where-Object {{ $_.IPAddress }} | Select-Object -First 1
$rt = $f | Where-Object {{ $_.DestinationPrefix }} | Select-Object -First 1
[pscustomobject]@{{
  adapters  = @(Get-NetAdapter | Select-Object Name, InterfaceDescription, ifIndex, @{{n='Status';e={{"$($_.Status)"}}}}, MacAddress)
  addresses = @(Get-NetIPAddress -AddressFamily IPv4 | Select-Object InterfaceAlias, ifIndex, IPAddress, PrefixLength, @{{n='AddressState';e={{"$($_.AddressState)"}}}})
  routes    = @(Get-NetRoute -AddressFamily IPv4 | Select-Object DestinationPrefix, NextHop, ifIndex, InterfaceAlias)
  find      = [pscustomobject]@{{ source = $src.IPAddress; ifIndex = $rt.ifIndex; alias = $rt.InterfaceAlias; prefix = $rt.DestinationPrefix; nexthop = $rt.NextHop }}
  neighbors = @(Get-NetNeighbor -IPAddress $cam | Select-Object InterfaceAlias, ifIndex, LinkLayerAddress, @{{n='State';e={{"$($_.State)"}}}})
}} | ConvertTo-Json -Depth 4 -Compress
"""


def _is_ll(addr: str) -> bool:
    try:
        return ipaddress.ip_address(addr) in LINK_LOCAL
    except ValueError:
        return False


def _mac(m) -> str:
    return (m or "").upper().replace(":", "-")


def evaluate(snap: dict, camera_ip: str = CAMERA_A_IP, camera_mac: str = CAMERA_A_MAC):
    """Pure check of a snapshot. Returns (ok, problems, facts)."""
    problems, facts = [], {"camera_ip": camera_ip, "camera_mac": _mac(camera_mac)}
    if not _is_ll(camera_ip):
        problems.append("camera address {} is not link-local".format(camera_ip))
    adapters = {a["ifIndex"]: a for a in snap.get("adapters") or []}
    addrs = snap.get("addresses") or []
    routes = snap.get("routes") or []
    f = snap.get("find") or {}
    x = f.get("ifIndex")
    facts["selected_route"] = f
    if x is None:
        problems.append("the OS has no route to the camera")
        return False, problems, facts
    ad = adapters.get(x, {})
    facts["camera_interface"] = {"ifIndex": x, "alias": f.get("alias"), "description": ad.get("InterfaceDescription"), "status": ad.get("Status")}
    if not _is_ll(f.get("source") or ""):
        problems.append("source address for the camera ({}) is not link-local".format(f.get("source")))
    if (ad.get("Status") or "").lower() != "up":
        problems.append("camera interface {} is not Up ({})".format(f.get("alias"), ad.get("Status")))
    desc = ((ad.get("InterfaceDescription") or "") + " " + (ad.get("Name") or "")).lower()
    if any(w in desc for w in WIRELESS_WORDS):
        problems.append("camera route uses a wireless adapter ({})".format(ad.get("InterfaceDescription")))
    on_x = [a for a in addrs if a.get("ifIndex") == x]
    if not any(_is_ll(a["IPAddress"]) and (a.get("AddressState") or "").lower() == "preferred" for a in on_x):
        problems.append("camera interface has no Preferred link-local address")
    non_ll_x = [a["IPAddress"] for a in on_x if not _is_ll(a["IPAddress"]) and not a["IPAddress"].startswith("127.")]
    if non_ll_x:
        problems.append("camera interface also carries non-link-local addresses {}".format(non_ll_x))
    rx = [r for r in routes if r.get("ifIndex") == x]
    if any(r.get("DestinationPrefix") == "0.0.0.0/0" for r in rx):
        problems.append("camera interface has a default route")
    if not any(r.get("DestinationPrefix") == "169.254.0.0/16" for r in rx):
        problems.append("camera interface has no 169.254.0.0/16 route")
    # other interfaces offering a link-local route with a usable link-local address
    other_ll = []
    for r in routes:
        i = r.get("ifIndex")
        if i == x or r.get("DestinationPrefix") != "169.254.0.0/16":
            continue
        st = (adapters.get(i, {}).get("Status") or "").lower()
        pref = any(a.get("ifIndex") == i and _is_ll(a["IPAddress"]) and (a.get("AddressState") or "").lower() == "preferred" for a in addrs)
        if pref and st in ("up", ""):
            other_ll.append(r.get("InterfaceAlias"))
    if other_ll:
        problems.append("another connected interface also offers the link-local network: {}".format(other_ll))
    overlaps = []
    for a in addrs:
        if a.get("ifIndex") == x or a["IPAddress"].startswith("127.") or _is_ll(a["IPAddress"]):
            continue
        try:
            net = ipaddress.ip_network("{}/{}".format(a["IPAddress"], a["PrefixLength"]), strict=False)
        except ValueError:
            continue
        if net.overlaps(LINK_LOCAL):
            overlaps.append(str(net))
    if overlaps:
        problems.append("subnet(s) overlapping 169.254.0.0/16 on other interfaces: {}".format(overlaps))
    facts["other_interfaces_non_link_local"] = sorted({"{} {}".format(a.get("InterfaceAlias"), a["IPAddress"]) for a in addrs
                                                       if a.get("ifIndex") != x and not _is_ll(a["IPAddress"]) and not a["IPAddress"].startswith("127.")
                                                       and (a.get("AddressState") or "").lower() == "preferred"})
    neigh = snap.get("neighbors") or []
    facts["arp"] = neigh
    on_x_n = [n for n in neigh if n.get("ifIndex") == x]
    good = [n for n in on_x_n if _mac(n.get("LinkLayerAddress")) == _mac(camera_mac) and (n.get("State") or "").lower() in GOOD_ARP_STATES]
    if not good:
        problems.append("ARP on the camera interface does not show the recorded camera MAC {} ({})".format(_mac(camera_mac), on_x_n))
    elsewhere = [n for n in neigh if n.get("ifIndex") != x and _mac(n.get("LinkLayerAddress")) not in ("", "00-00-00-00-00-00")]
    if elsewhere:
        problems.append("the camera address is also known on another interface: {}".format(elsewhere))
    return not problems, problems, facts


def snapshot(camera_ip: str = CAMERA_A_IP, timeout_s: float = 30.0) -> dict:
    """Read-only Windows snapshot (PowerShell). Raises RuntimeError if it cannot be taken."""
    ipaddress.ip_address(camera_ip)      # validated before it reaches the command line
    cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", PS_SNAPSHOT.format(ip=camera_ip)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    if p.returncode != 0 or not p.stdout.strip():
        raise RuntimeError("network snapshot failed (exit {}): {}".format(p.returncode, p.stderr.strip()[:300]))
    data = json.loads(p.stdout)
    for k in ("adapters", "addresses", "routes", "neighbors"):      # ConvertTo-Json turns a 1-item array into an object
        v = data.get(k)
        data[k] = [] if v is None else v if isinstance(v, list) else [v]
    return data


def check_now(camera_ip: str = CAMERA_A_IP, camera_mac: str = CAMERA_A_MAC):
    snap = snapshot(camera_ip)
    ok, problems, facts = evaluate(snap, camera_ip, camera_mac)
    return {"ok": ok, "problems": problems, "facts": facts, "mode": "ethernet_scoped"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Ethernet-scoped network check (read-only)")
    ap.add_argument("--camera-ip", default=CAMERA_A_IP)
    ap.add_argument("--camera-mac", default=CAMERA_A_MAC)
    ap.add_argument("--json", help="also write the result here")
    a = ap.parse_args(argv)
    try:
        res = check_now(a.camera_ip, a.camera_mac)
    except Exception as exc:            # noqa: BLE001
        print(json.dumps({"ok": False, "error": "{}: {}".format(type(exc).__name__, exc)}))
        return 3
    text = json.dumps(res, indent=1)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    return 0 if res["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
