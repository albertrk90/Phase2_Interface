"""Offline tests for the ethernet-scoped network mode (12 Nov 2026). No camera, no network change.

* network_scope.evaluate: PASS for the observed concurrent Wi-Fi + Ethernet state and for Ethernet only; REFUSES
  when the camera route uses Wi-Fi or a wireless adapter, when another interface also offers the link-local
  network, when the camera interface has a non-link-local address or a default route, on an overlapping subnet,
  on an ARP MAC mismatch / missing entry / entry on another interface, and for a non-link-local camera address;
* camera_gateway_a in --network-scope ethernet_scoped with the fake DepthAI device: no broadcast discovery at all
  (unicast DeviceInfo only), the full safety order, a refused pre-check contacts nothing, and a scope change while
  streaming stops the run (network_scope_changed, exit 1) with the pipeline stopped, the device closed and the
  post-run calibration read still done; the argument refusals; the default stays "isolated".
Run: camera_gateway\\.venv\\Scripts\\python.exe -I camera_gateway\\tests\\test_network_scope.py
"""
import copy
import json
import pathlib
import sys
import tempfile
import types

sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
GW = HERE.parent
sys.path[:0] = [str(GW), str(GW / "tools"), str(HERE)]

import camera_gateway_a as cga  # noqa: E402
import fake_dai  # noqa: E402
import network_scope as ns  # noqa: E402
import standin_encoder as se  # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (("  -- " + str(detail)[:400]) if detail and not cond else ""))


# ------------------------------------------------------------------ the observed state (12 Nov 2026, 18:15)
BASE = {
    "adapters": [
        {"Name": "WiFi", "InterfaceDescription": "Intel(R) Wi-Fi 6E AX211 160MHz", "ifIndex": 8, "Status": "Up", "MacAddress": "E0-C2-64-B6-DB-EA"},
        {"Name": "Ethernet 4", "InterfaceDescription": "Realtek USB GbE Family Controller #3", "ifIndex": 10, "Status": "Up", "MacAddress": "D0-AD-08-EA-89-C3"},
        {"Name": "Bluetooth Network Connection", "InterfaceDescription": "Bluetooth Device (Personal Area Network)", "ifIndex": 19, "Status": "Disconnected", "MacAddress": "E0-C2-64-B6-DB-EE"},
    ],
    "addresses": [
        {"InterfaceAlias": "WiFi", "ifIndex": 8, "IPAddress": "10.12.58.66", "PrefixLength": 18, "AddressState": "Preferred"},
        {"InterfaceAlias": "Ethernet 4", "ifIndex": 10, "IPAddress": "169.254.80.246", "PrefixLength": 16, "AddressState": "Preferred"},
        {"InterfaceAlias": "Bluetooth Network Connection", "ifIndex": 19, "IPAddress": "169.254.148.64", "PrefixLength": 16, "AddressState": "Tentative"},
        {"InterfaceAlias": "Loopback Pseudo-Interface 1", "ifIndex": 1, "IPAddress": "127.0.0.1", "PrefixLength": 8, "AddressState": "Preferred"},
    ],
    "routes": [
        {"DestinationPrefix": "0.0.0.0/0", "NextHop": "10.12.63.254", "ifIndex": 8, "InterfaceAlias": "WiFi"},
        {"DestinationPrefix": "10.12.0.0/18", "NextHop": "0.0.0.0", "ifIndex": 8, "InterfaceAlias": "WiFi"},
        {"DestinationPrefix": "169.254.0.0/16", "NextHop": "0.0.0.0", "ifIndex": 10, "InterfaceAlias": "Ethernet 4"},
        {"DestinationPrefix": "169.254.0.0/16", "NextHop": "0.0.0.0", "ifIndex": 19, "InterfaceAlias": "Bluetooth Network Connection"},
    ],
    "find": {"source": "169.254.80.246", "ifIndex": 10, "alias": "Ethernet 4", "prefix": "169.254.0.0/16", "nexthop": "0.0.0.0"},
    "neighbors": [{"InterfaceAlias": "Ethernet 4", "ifIndex": 10, "LinkLayerAddress": "44-A9-2C-32-3C-AC", "State": "Reachable"}],
}


def variant(fn):
    s = copy.deepcopy(BASE)
    fn(s)
    return ns.evaluate(s)


ok, probs, facts = ns.evaluate(BASE)
check("observed concurrent Wi-Fi + Ethernet state passes; Wi-Fi recorded as another interface", ok and facts["other_interfaces_non_link_local"] == ["WiFi 10.12.58.66"], probs)
ok, probs, _ = variant(lambda s: (s["addresses"].pop(0), s["routes"].pop(0), s["routes"].pop(0)))
check("Ethernet only (Wi-Fi off) also passes", ok, probs)


def refused(name, fn, word):
    ok, probs, _ = variant(fn)
    check("refused: " + name, not ok and any(word in p for p in probs), probs)


refused("camera route via Wi-Fi", lambda s: s.update(find={"source": "10.12.58.66", "ifIndex": 8, "alias": "WiFi", "prefix": "0.0.0.0/0", "nexthop": "10.12.63.254"}), "not link-local")
refused("camera route on a wireless adapter", lambda s: s["adapters"][1].update(InterfaceDescription="USB Wireless LAN 802.11ac"), "wireless")
refused("another connected interface offers the link-local network (Wi-Fi APIPA)", lambda s: (
    s["addresses"].append({"InterfaceAlias": "WiFi", "ifIndex": 8, "IPAddress": "169.254.9.9", "PrefixLength": 16, "AddressState": "Preferred"}),
    s["routes"].append({"DestinationPrefix": "169.254.0.0/16", "NextHop": "0.0.0.0", "ifIndex": 8, "InterfaceAlias": "WiFi"})), "another connected interface")
refused("non-link-local address on the camera interface", lambda s: s["addresses"].append(
    {"InterfaceAlias": "Ethernet 4", "ifIndex": 10, "IPAddress": "192.168.1.5", "PrefixLength": 24, "AddressState": "Preferred"}), "non-link-local addresses")
refused("default route on the camera interface", lambda s: s["routes"].append(
    {"DestinationPrefix": "0.0.0.0/0", "NextHop": "169.254.1.1", "ifIndex": 10, "InterfaceAlias": "Ethernet 4"}), "default route")
refused("overlapping subnet on another interface", lambda s: s["addresses"].append(
    {"InterfaceAlias": "WiFi", "ifIndex": 8, "IPAddress": "169.0.0.5", "PrefixLength": 8, "AddressState": "Preferred"}), "overlapping")
refused("ARP MAC mismatch", lambda s: s["neighbors"][0].update(LinkLayerAddress="44-A9-2C-37-BA-5D"), "recorded camera MAC")
refused("ARP entry missing (camera not answering)", lambda s: s.update(neighbors=[]), "recorded camera MAC")
refused("ARP unreachable", lambda s: s["neighbors"][0].update(LinkLayerAddress="00-00-00-00-00-00", State="Unreachable"), "recorded camera MAC")
refused("camera address known on another interface", lambda s: s["neighbors"].append(
    {"InterfaceAlias": "WiFi", "ifIndex": 8, "LinkLayerAddress": "44-A9-2C-32-3C-AC", "State": "Reachable"}), "another interface")
refused("camera interface down", lambda s: s["adapters"][1].update(Status="Disconnected"), "not Up")
refused("no route to the camera", lambda s: s.update(find={}), "no route")
ok, probs, _ = ns.evaluate(BASE, camera_ip="10.12.58.1")
check("refused: non-link-local camera address", not ok and any("not link-local" in p for p in probs), probs)
check("a 1-item ConvertTo-Json object would be normalised (snapshot keys are lists)", all(isinstance(BASE[k], list) for k in ("adapters", "addresses", "routes", "neighbors")))

# ------------------------------------------------------------------ the gateway in ethernet_scoped mode (fake DepthAI)
PAIRS = se.load_e1_pairs()
LEFT = [PAIRS[i % 5][1] for i in range(45)]
RIGHT = [PAIRS[i % 5][2] for i in range(45)]
AU_L, AU_R = se.encode_sequence(LEFT, keyint=20), se.encode_sequence(RIGHT, keyint=20)
cs, cc, dc = cga.load_safety_modules()
work = pathlib.Path(tempfile.mkdtemp(prefix="gwscope_"))


def args_for(d, user, factory, extra=()):
    (d / "u.json").write_text(json.dumps(user), encoding="utf-8")
    (d / "f.json").write_text(json.dumps(factory), encoding="utf-8")
    return cga.parse_args(["--expect", "169.254.1.222=19443010B14C872F00", "--baseline-user", str(d / "u.json"), "--baseline-factory",
                           str(d / "f.json"), "--seconds", "5", "--sink", "file", "--post-verify-wait-s", "5", "--frame-timeout-s", "1.0",
                           "--network-scope", "ethernet_scoped", "--scope-check-interval-s", "1", *extra], dc)


def scoped_run(name, scope_results, **kw):
    d = work / name
    d.mkdir()
    calls = []
    fake, user, factory = fake_dai.make_fake_dai(calls, AU_L, AU_R, autocal_sticks=False, **kw)
    real_broadcast = fake.Device.getAllAvailableDevices
    fake.Device.getAllAvailableDevices = staticmethod(lambda: (calls.append("BROADCAST"), real_broadcast())[1])
    fake.DeviceInfo = lambda ip: (calls.append("unicast:" + ip), types.SimpleNamespace(name=ip))[1]
    seq = list(scope_results)

    def scope():
        calls.append("scope_check")
        return seq.pop(0) if len(seq) > 1 else seq[0]
    a = args_for(d, user, factory)
    rep = {}
    code = cga.run(fake, a, d, rep, cs, cc, dc, scope_check=scope)
    return code, rep, calls


GOOD = {"ok": True, "problems": [], "facts": {}}
BAD = {"ok": False, "problems": ["camera route uses a wireless adapter"], "facts": {}}

code, rep, calls = scoped_run("ok", [GOOD])
check("scoped run: exit 0, seconds reached, calibration unchanged, pipeline stopped, device closed",
      code == 0 and rep["stop_reason"] == "seconds_reached" and rep["calibration_unchanged"] is True and rep["pipeline_stopped"] and rep["device_closed"],
      (code, rep.get("stop_reason"), rep.get("errors")))
check("scoped run: NO broadcast discovery; unicast to the camera IP for the connection and the post-run read",
      "BROADCAST" not in calls and calls.count("unicast:169.254.1.222") == 2, [c for c in calls if c.startswith(("unicast", "BROADCAST"))])
order = [c for c in calls if c in ("scope_check", "device_open", "read_user_calibration", "ir_dot_0.0", "autocal_get_OFF", "pipeline_start",
                                    "pipeline_stop", "device_close")]
check("scoped run: scope check before any contact, then the validated safety order",
      order[:2] == ["scope_check", "device_open"] and order.index("autocal_get_OFF") < order.index("pipeline_start") < order.index("pipeline_stop"), order)
check("scoped run: the scope was re-checked while streaming", rep["network_scope"]["monitor"]["checks_while_streaming"] >= 2, rep.get("network_scope"))
check("scoped run: selection recorded as unicast; identity verified", rep["selection"]["actual_device_id"] == "19443010B14C872F00"
      and "unicast" in rep["selection"]["method"], rep.get("selection"))
check("scoped run: post-run calibration read by unicast, read_ok", rep["calibration_post_run"]["status"] == "read_ok"
      and "unicast" in rep["calibration_post_run"]["method"], rep.get("calibration_post_run"))
check("scoped run: no forbidden device call", not [c for c in calls if c.startswith("FORBIDDEN")])

code, rep, calls = scoped_run("refused", [BAD])
check("scoped pre-check refused: safety abort, NOTHING contacted (no device open, no broadcast, no unicast)",
      code == 1 and rep["stop_reason"] == "safety_abort" and "device_open" not in calls and not [c for c in calls if c.startswith(("unicast", "BROADCAST"))],
      (code, rep.get("stop_reason"), calls[:5]))

code, rep, calls = scoped_run("changed", [GOOD, GOOD, BAD])
check("scope change while streaming: stop reason network_scope_changed, exit 1", code == 1 and rep["stop_reason"] == "network_scope_changed",
      (code, rep.get("stop_reason"), rep.get("errors")))
check("scope change while streaming: pipeline stopped, device closed, post-run read still done, calibration unchanged",
      rep["pipeline_stopped"] and rep["device_closed"] and rep["calibration_post_run"]["status"] == "read_ok" and rep["calibration_unchanged"] is True, rep.get("errors"))

code, rep, calls = scoped_run("wrong_id", [GOOD], device_id="194430108183F12E00")
check("scoped run: identity mismatch after the unicast connect -> device closed, safety abort", code == 1 and rep["stop_reason"] == "safety_abort"
      and "device_close" in calls and "pipeline_start" not in calls, (rep.get("stop_reason"), rep.get("errors")))

d = work / "args"
d.mkdir()
(d / "u.json").write_text("{}", encoding="utf-8")
(d / "f.json").write_text("{}", encoding="utf-8")
base_argv = ["--expect", "169.254.1.222=19443010B14C872F00", "--baseline-user", str(d / "u.json"), "--baseline-factory", str(d / "f.json")]
a = cga.parse_args(base_argv, dc)
check("default network scope is the validated 'isolated' (broadcast pre-check)", a.network_scope == "isolated"
      and cga.plan(a)["device_selection"].startswith("broadcast"), cga.plan(a)["device_selection"])
for name, extra in (("ethernet_scoped with --allow-non-isolated", ["--network-scope", "ethernet_scoped", "--allow-non-isolated"]),
                    ("bad --camera-mac", ["--camera-mac", "nope"]), ("--scope-check-interval-s out of range", ["--scope-check-interval-s", "0.1"])):
    try:
        cga.parse_args(base_argv + extra, dc)
        check("argument refused: " + name, False)
    except SystemExit:
        check("argument refused: " + name, True)

n_fail = sum(1 for _, ok in RESULTS if not ok)
print("{} checks, {} failed".format(len(RESULTS), n_fail))
sys.exit(1 if n_fail else 0)
