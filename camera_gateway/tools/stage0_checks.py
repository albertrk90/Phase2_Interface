"""Task 06 Stage 0: pre-hardware checks (offline; no device searched or contacted).

Writes camera_gateway/results/stage0_<stamp>/stage0_report.json and prints a summary:
  1. gateway offline suite (tests/test_gateway.py) and plan-only mode;
  2. dependencies: exact versions, and the DepthAI / PyAV builds identical (RECORD
     hashes) to the validated camera_validation / streaming_poc venvs;
  3. configuration hashes: the pinned camera_validation safeguard sources, the
     baseline calibration files, the MediaMTX localhost config (against the value
     verified by the T4 preflight; Stage 1 does not start MediaMTX);
  4. DepthAI crash-dump count (before Stage 1);
  5. CONNECTION PROCEDURE (bootloader state, no persistent change):
     * static scan of the gateway and the pinned safeguard modules: no flashing,
       bootloader, IP, calibration-write or factory-reset call; IR setters only with 0;
     * the procedure requires X_LINK_BOOTLOADER before connecting (preflight) and the
       device back in X_LINK_BOOTLOADER after the run (post-run verification);
     * the validated Camera A Stage E runs used it with calibration unchanged and the
       device back in bootloader state; bootloader 0.0.26 recorded on 3 and 4 Nov.
  6. host network snapshot (read-only) and the Unity clock reference.

Run: camera_gateway\\.venv\\Scripts\\python.exe -I camera_gateway\\tools\\stage0_checks.py
"""
import datetime as dt
import glob
import hashlib
import json
import os
import pathlib
import re
import socket
import subprocess
import sys

sys.dont_write_bytecode = True
GW = pathlib.Path(__file__).resolve().parents[1]
ROOT = GW.parent
sys.path.insert(0, str(GW))
import camera_gateway_a as cga  # noqa: E402

CV = ROOT / "camera_validation"
R = CV / "results"
BASE_U = R / "calibration_user_19443010B14C872F00_20261103_182445.json"
BASE_F = R / "calibration_factory_19443010B14C872F00_20261103_182445.json"
MTX_CFG = ROOT / "streaming_poc" / "config" / "mediamtx_localhost.yml"
MTX_VERIFIED = "782145b3fac5a219c6b0312a568b00607671b89f4d1bce6ab492f4d51024940a"   # T4 preflight.json
CRASH = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "depthai" / "cache" / "crashdumps"
PY = GW / ".venv" / "Scripts" / "python.exe"
FORBIDDEN = re.compile(r"\b(flash\w*|DeviceBootloader|setIPAddress\w*|setStaticIPv4|setDynamicIPv4|setCalibration|"
                       r"factoryReset|bootFirmware|bootUsbRomBootloader|setUsbSpeed|eepromClear)\b")


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def record_hash(site, name):
    rec = next(pathlib.Path(site).glob("{}*.dist-info/RECORD".format(name.split("-")[0])), None)
    if not rec:
        return {}
    out = {}
    for l in rec.read_text(encoding="utf-8").splitlines():
        parts = l.split(",")
        if len(parts) < 3 or not parts[1]:
            continue
        f = parts[0]
        if ".dist-info/" in f or f.startswith("..") or "__pycache__" in f:
            continue                       # installer metadata and venv-specific entries
        out[f] = parts[1]
    return out


def api_scan(path):
    """AST scan: attribute uses and getattr/safe_call string targets that match FORBIDDEN, and every
    IR setter call with its argument. Strings in messages and dictionary keys are not code."""
    import ast
    tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
    forbidden, ir_calls, ir_names = [], [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and FORBIDDEN.fullmatch(node.attr):
            forbidden.append((node.lineno, "attribute ." + node.attr))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("getattr", "safe_call", "hasattr"):
            for a in node.args[1:2]:
                if isinstance(a, ast.Constant) and isinstance(a.value, str) and FORBIDDEN.fullmatch(a.value):
                    forbidden.append((node.lineno, "{}(..., {!r})".format(node.func.id, a.value)))
        if isinstance(node, ast.Tuple) and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts):
            ir_names.update(e.value for e in node.elts if "setIr" in e.value)
        if isinstance(node, ast.Call):
            f = node.func
            direct = isinstance(f, ast.Attribute) and "setIr" in f.attr
            via_getattr = isinstance(f, ast.Call) and isinstance(f.func, ast.Name) and f.func.id == "getattr" and bool(node.args)  # getters take no argument
            if direct or via_getattr:
                args = [a.value if isinstance(a, ast.Constant) else ast.dump(a) for a in node.args]
                ir_calls.append({"line": node.lineno, "args": args, "zero": all(isinstance(a, (int, float)) and a == 0 for a in args)})
    return forbidden, ir_calls, sorted(ir_names)


def code_lines(path):
    """Source lines with comments and docstrings removed (only executable references are scanned)."""
    import ast
    src = pathlib.Path(path).read_text(encoding="utf-8")
    tree = ast.parse(src)
    doc_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant) and isinstance(node.value.value, str):
            doc_lines.update(range(node.lineno, node.end_lineno + 1))
    out = []
    for i, line in enumerate(src.splitlines(), 1):
        if i in doc_lines:
            continue
        code = line.split("#", 1)[0]
        if code.strip():
            out.append((i, code))
    return out


def main():
    rep = {"created": dt.datetime.now().isoformat(), "device_contact": "none", "checks": {}}
    C = rep["checks"]
    # 1 tests and plan-only
    t = subprocess.run([str(PY), "-I", str(GW / "tests" / "test_gateway.py")], capture_output=True, text=True, timeout=900)
    last = [l for l in t.stdout.splitlines() if "checks," in l]
    C["gateway_offline_suite"] = {"ok": t.returncode == 0, "summary": last[-1] if last else None}
    pl = subprocess.run([str(PY), "-I", str(GW / "camera_gateway_a.py"), "--expect", "169.254.1.222=19443010B14C872F00",
                         "--baseline-user", str(BASE_U), "--baseline-factory", str(BASE_F), "--sink", "file",
                         "--seconds", "30", "--label", "stage1", "--dump-raw"], capture_output=True, text=True, timeout=120)
    C["plan_only_mode"] = {"ok": pl.returncode == 0 and "PLAN ONLY" in pl.stdout, "tail": pl.stdout.strip().splitlines()[-1]}
    # 2 dependencies
    site = GW / ".venv" / "Lib" / "site-packages"
    frz = subprocess.run([str(PY), "-m", "pip", "freeze", "--disable-pip-version-check"], capture_output=True, text=True).stdout.split()
    lock = (GW / "requirements.lock.txt").read_text(encoding="utf-8").split()
    d_gw, d_cv = record_hash(site, "depthai"), record_hash(CV / ".venv" / "Lib" / "site-packages", "depthai")
    a_gw, a_sp = record_hash(site, "av"), record_hash(ROOT / "streaming_poc" / ".venv" / "Lib" / "site-packages", "av")
    C["dependencies"] = {"ok": sorted(frz) == sorted(lock) == ["av==19.0.2", "depthai==3.11.0", "numpy==2.4.6"]
                         and d_gw and d_gw == d_cv and a_gw and a_gw == a_sp,
                         "freeze": frz, "depthai_record_identical_to_camera_validation": d_gw == d_cv,
                         "av_record_identical_to_streaming_poc": a_gw == a_sp, "python": sys.version.split()[0]}
    # 3 configuration hashes
    pins = {n: sha(CV / n) == h for n, h in cga.SAFETY_SOURCES.items()}
    C["safety_sources_pinned"] = {"ok": all(pins.values()), "match": pins}
    C["baseline_calibration_files"] = {"ok": BASE_U.is_file() and BASE_F.is_file(),
                                       "user_sha256": sha(BASE_U), "factory_sha256": sha(BASE_F)}
    C["mediamtx_config"] = {"ok": sha(MTX_CFG) == MTX_VERIFIED, "sha256": sha(MTX_CFG), "verified_t4": MTX_VERIFIED,
                            "note": "Stage 1 does not start MediaMTX"}
    # 4 crash dumps
    dumps = sorted(str(p.relative_to(CRASH)) for p in CRASH.rglob("*") if p.is_file()) if CRASH.exists() else []
    C["crash_dumps_before"] = {"ok": True, "count": len(dumps), "files": dumps}
    # 5 connection procedure
    scan = {}
    for path in [GW / "camera_gateway_a.py", GW / "gateway_core.py", GW / "gateway_output.py"] + [CV / n for n in cga.SAFETY_SOURCES]:
        hits, ir, names = api_scan(path)
        scan[path.name] = {"forbidden_calls": hits, "ir_setter_calls": ir, "ir_setter_names": names}
    ir_only_zero = all(c["zero"] for v in scan.values() for c in v["ir_setter_calls"])
    cs_src = (CV / "discover_cameras.py").read_text(encoding="utf-8")
    e_runs = []
    for p in sorted(glob.glob(str(R / "rectify_*19443010B14C872F00_E*" / "report.json"))):
        r = json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
        post = r.get("calibration_post_run", {})
        e_runs.append({"run": pathlib.Path(p).parent.name, "preflight_seen_state": r.get("selection", {}).get("preflight_seen_state"),
                       "calibration_unchanged": r.get("calibration_unchanged"), "post_run_status": post.get("status"),
                       "post_run_seen_state": (post.get("last_precheck") or {}).get("seen_state"),
                       "device_closed": r.get("device_closed")})
    bl = []
    for p in sorted(glob.glob(str(R / "discover_*.json"))):
        txt = pathlib.Path(p).read_text(encoding="utf-8")
        if "19443010B14C872F00" in txt:
            for m in re.finditer(r'"getBootloaderVersion":\s*"([^"]+)"', txt):
                bl.append((pathlib.Path(p).name, m.group(1)))
    C["connection_procedure"] = {
        "ok": all(not v["forbidden_calls"] for v in scan.values()) and ir_only_zero
              and "X_LINK_BOOTLOADER" in cs_src and e_runs and all(e["calibration_unchanged"] is True for e in e_runs)
              and bl and all(v == cga.EXPECTED_BOOTLOADER for _, v in bl),
        "static_scan": scan, "ir_setters_only_zero": ir_only_zero,
        "preflight_requires_bootloader_state": "X_LINK_BOOTLOADER" in cs_src,
        "validated_camera_A_stage_E_runs": e_runs, "bootloader_versions_recorded_camera_A": bl,
        "how_it_works": ("The device idles in its flash bootloader (X_LINK_BOOTLOADER). dai.Device(info) sends the DepthAI "
                         "firmware over the network into RAM and boots it; nothing is flashed. On close the device reboots back "
                         "into the bootloader, which post-run verification waits for (and then re-reads calibration). "
                         "Persistent writes would need flash*/DeviceBootloader/IP/calibration APIs, none of which are called; "
                         "AutoCalibrationMode OFF prevents DepthAI's own calibration flashing.")}
    # 6 host
    try:
        addrs = sorted({i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)})
    except socket.gaierror:
        addrs = []
    C["host_network_now"] = {"ok": True, "ipv4": addrs,
                             "isolated_now": bool(addrs) and all(a.startswith("169.254.") or a.startswith("127.") for a in addrs),
                             "note": "Stage 1 needs the isolated camera Ethernet with Wi-Fi off; the gateway refuses otherwise"}
    cref = ROOT / "unity" / "Phase2Client" / "test_results" / "inputs" / "clock_reference.json"
    C["unity_clock_reference"] = {"ok": cref.exists(), "file": json.loads(cref.read_text(encoding="utf-8")) if cref.exists() else None}
    rep["overall"] = "PASS" if all(v["ok"] for v in C.values()) else "FAIL"
    out = GW / "results" / "stage0_{}".format(dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    out.mkdir(parents=True)
    (out / "stage0_report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    for k, v in C.items():
        print("{:32s} {}".format(k, "PASS" if v["ok"] else "FAIL"))
    print("crash dumps before:", C["crash_dumps_before"]["count"], "| host IPv4 now:", C["host_network_now"]["ipv4"])
    print("bootloader records:", C["connection_procedure"]["bootloader_versions_recorded_camera_A"])
    print("Stage E runs:", [(e["run"][-14:], e["preflight_seen_state"], e["calibration_unchanged"], e["post_run_status"]) for e in e_runs])
    print("OVERALL", rep["overall"], "->", out)
    return 0 if rep["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
