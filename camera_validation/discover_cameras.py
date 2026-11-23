"""Discover Luxonis OAK PoE cameras and record identity, sensors and calibration availability.

Read-only with respect to the camera. Connecting uploads the DepthAI runtime
firmware into device RAM for the session (standard DepthAI behaviour, cleared
on power-cycle); this script never flashes firmware, changes bootloader
settings, or writes EEPROM/calibration. No pipeline is started, so the IR dot
projector and flood illuminator stay off.

Run from the camera_validation folder:

    .venv\\Scripts\\python.exe discover_cameras.py --ip 169.254.1.222
    .venv\\Scripts\\python.exe discover_cameras.py --ip 169.254.1.222 --ip 169.254.1.223 --simultaneous
    .venv\\Scripts\\python.exe discover_cameras.py --broadcast --no-connect
    .venv\\Scripts\\python.exe discover_cameras.py --expect 169.254.1.222=19443010B14C872F00 --expect 169.254.1.223=194430108183F12E00

--ip connects directly to a known address (unicast, no search). It checks only
the IP, so on a network with an address conflict it can boot the wrong camera.
--broadcast runs DepthAI's network discovery, which is refused unless every
active IPv4 address on the laptop is link-local (169.254.x.x), i.e. the laptop
is attached only to the isolated camera network.
--expect IP=DEVICE_ID is the verified mode. It first runs broadcast discovery
and boots nothing unless every expected camera is seen exactly once, at its IP,
with its device ID, in bootloader state. It then connects to each camera in turn
(selected by IP and device ID), rejects and closes any connection whose reported
ID or IP differs, holds the verified connections open together for
--hold-seconds, and closes them all, even if one fails.
"""

import argparse
import contextlib
import datetime as dt
import ipaddress
import json
import logging
import os
import platform
import re
import socket
import sys
import time
import traceback
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent / "results"
CRASHDUMP_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "depthai" / "cache" / "crashdumps"
log = logging.getLogger("discover")

DEVICE_GETTERS = (
    "getDeviceId", "getDeviceName", "getProductName", "getPlatformAsString",
    "getBootloaderVersion", "getConnectedCameras", "getCameraSensorNames",
    "getConnectedCameraFeatures", "getAvailableStereoPairs", "getIrDrivers",
    "getConnectedIMU", "getChipTemperature",
)
EEPROM_FIELDS = (
    "boardName", "productName", "boardRev", "boardConf", "hardwareConf", "batchName",
    "batchTime", "deviceName", "version",
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ip", action="append", default=[], help="camera IP to connect to directly (repeatable)")
    parser.add_argument("--broadcast", action="store_true", help="run DepthAI broadcast discovery (isolated network only)")
    parser.add_argument("--allow-non-isolated", action="store_true",
                        help="permit --broadcast while non-link-local IPv4 addresses are active")
    parser.add_argument("--no-connect", action="store_true", help="list discovered devices without connecting")
    parser.add_argument("--simultaneous", action="store_true", help="hold all connections open at the same time")
    parser.add_argument("--expect", action="append", default=[], metavar="IP=DEVICE_ID",
                        help="verified mode: camera expected at IP with DEVICE_ID (repeatable)")
    parser.add_argument("--hold-seconds", type=float, default=5.0,
                        help="--expect: how long to hold all verified connections open together (0-60)")
    parser.add_argument("--stagger-seconds", type=float, default=3.0,
                        help="--expect: pause between successive connections (0-30)")
    parser.add_argument("--connect-timeout-ms", type=int, default=15000)
    args = parser.parse_args()
    if args.expect:
        if args.ip or args.broadcast or args.no_connect or args.simultaneous:
            parser.error("--expect cannot be combined with --ip, --broadcast, --no-connect or --simultaneous")
        if not 0 <= args.hold_seconds <= 60 or not 0 <= args.stagger_seconds <= 30:
            parser.error("--hold-seconds must be 0-60 and --stagger-seconds 0-30")
        args.expect = [parse_expectation(parser, item) for item in args.expect]
        ips = [ip for ip, _ in args.expect]
        ids = [device_id for _, device_id in args.expect]
        if len(set(ips)) != len(ips) or len(set(ids)) != len(ids):
            parser.error("each --expect IP and DEVICE_ID must be unique")
    elif not args.ip and not args.broadcast:
        parser.error("give at least one --ip, --broadcast or --expect")
    return args


def parse_expectation(parser, item):
    ip, sep, device_id = item.partition("=")
    device_id = device_id.strip().upper()
    if not sep or not re.fullmatch(r"[0-9A-F]{18}", device_id):
        parser.error(f"--expect {item!r}: use IP=DEVICE_ID with an 18-character hexadecimal device ID")
    try:
        if not ipaddress.ip_address(ip.strip()).is_link_local:
            parser.error(f"--expect {item!r}: {ip} is not a link-local (169.254.x.x) address")
    except ValueError:
        parser.error(f"--expect {item!r}: {ip!r} is not an IPv4 address")
    return ip.strip(), device_id


def host_ipv4_addresses():
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except socket.gaierror:
        return []
    return sorted({info[4][0] for info in infos})


def is_isolated_address(address):
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_link_local or ip.is_loopback


def crash_dumps():
    if not CRASHDUMP_DIR.is_dir():
        return set()
    return {str(p) for p in CRASHDUMP_DIR.rglob("*") if p.is_file()}


def to_jsonable(obj, depth=0):
    """Best-effort conversion of DepthAI (pybind11) objects into JSON-friendly data."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v, depth + 1) for v in obj]
    if hasattr(obj, "tolist"):
        return obj.tolist()
    # pybind11 enums expose .name/.value; render them as e.g. "CameraBoardSocket.CAM_B".
    if depth >= 4 or (hasattr(obj, "name") and isinstance(getattr(obj, "value", None), int)):
        return str(obj)
    fields = {}
    for name in dir(obj):
        if name.startswith("_"):
            continue
        try:
            value = getattr(obj, name)
        except Exception:
            continue
        if not callable(value):
            fields[name] = to_jsonable(value, depth + 1)
    return fields or str(obj)


def safe_call(obj, method, *args):
    fn = getattr(obj, method, None)
    if fn is None:
        return {"unavailable": f"{method} not present in this DepthAI version"}
    try:
        return to_jsonable(fn(*args))
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def device_id_of(info):
    for getter in ("getDeviceId", "getMxId"):
        fn = getattr(info, getter, None)
        if fn:
            try:
                value = str(fn())
                if value:
                    return value
            except Exception:
                pass
    return str(getattr(info, "deviceId", "") or getattr(info, "mxid", "") or getattr(info, "name", "unknown"))


def read_calibration(dai, device, device_id, stamp):
    """Read user and factory calibration (read-only) and save full copies on the host."""
    out = {}
    try:
        calib = device.readCalibration()
    except Exception as exc:
        return {"error": f"readCalibration failed: {type(exc).__name__}: {exc}"}

    try:
        eeprom = calib.getEepromData()
        out["eeprom"] = {field: to_jsonable(getattr(eeprom, field, None)) for field in EEPROM_FIELDS}
        out["calibrated_sockets"] = [str(k) for k in getattr(eeprom, "cameraData", {}).keys()]
    except Exception as exc:
        out["eeprom"] = {"error": f"{type(exc).__name__}: {exc}"}

    left, right = dai.CameraBoardSocket.CAM_B, dai.CameraBoardSocket.CAM_C
    out["baseline_cm_calibrated"] = safe_call(calib, "getBaselineDistance", right, left, False)
    out["baseline_cm_spec"] = safe_call(calib, "getBaselineDistance", right, left, True)

    user_json = safe_call(calib, "eepromToJson")
    path = RESULTS_DIR / f"calibration_user_{device_id}_{stamp}.json"
    path.write_text(json.dumps(user_json, indent=2), encoding="utf-8")
    out["user_calibration_file"] = str(path)

    factory_fn = getattr(device, "readFactoryCalibration", None)
    if factory_fn is None:
        out["factory_calibration"] = "readFactoryCalibration not present in this DepthAI version"
    else:
        try:
            factory_json = to_jsonable(factory_fn().eepromToJson())
            path = RESULTS_DIR / f"calibration_factory_{device_id}_{stamp}.json"
            path.write_text(json.dumps(factory_json, indent=2), encoding="utf-8")
            out["factory_calibration_file"] = str(path)
            out["user_matches_factory"] = factory_json == user_json
        except Exception as exc:
            out["factory_calibration"] = f"not readable: {type(exc).__name__}: {exc}"
    return out


def describe_connected(dai, device, stamp):
    record = {"device_info_connected": to_jsonable(device.getDeviceInfo())}
    for method in DEVICE_GETTERS:
        record[method] = safe_call(device, method)
    record["calibration"] = read_calibration(dai, device, device_id_of(device.getDeviceInfo()), stamp)
    return record


def connect(dai, info, record):
    t0 = time.monotonic()
    try:
        device = dai.Device(info)
        record["connect_seconds"] = round(time.monotonic() - t0, 2)
        return device
    except Exception as exc:
        record["connect_seconds"] = round(time.monotonic() - t0, 2)
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["traceback"] = traceback.format_exc()
        log.error("[%s] connection failed after %.1f s: %s", record["label"], record["connect_seconds"], record["error"])
        return None


def summarise(record):
    lines = [f"--- {record['label']} ---"]
    if "error" in record:
        lines.append(f"  FAILED: {record['error']}")
        return lines
    calib = record.get("calibration", {})
    eeprom = calib.get("eeprom", {})
    lines += [
        f"  device id      : {record.get('getDeviceId')}",
        f"  device name    : {record.get('getDeviceName')}",
        f"  product name   : {record.get('getProductName')}",
        f"  eeprom board   : {eeprom.get('boardName')} rev {eeprom.get('boardRev')} / {eeprom.get('productName')}",
        f"  bootloader     : {record.get('getBootloaderVersion')}",
        f"  sensors        : {record.get('getCameraSensorNames')}",
        f"  IR drivers     : {record.get('getIrDrivers')}",
        f"  calib sockets  : {calib.get('calibrated_sockets')}",
        f"  baseline (cm)  : calibrated {calib.get('baseline_cm_calibrated')}, spec {calib.get('baseline_cm_spec')}",
        f"  user == factory: {calib.get('user_matches_factory', calib.get('factory_calibration'))}",
        f"  connect time   : {record.get('connect_seconds')} s",
    ]
    return lines


def close_device(record, device):
    """Close once and record whether the device reports itself closed."""
    if "closed" in record:
        return
    try:
        device.close()
        record["closed"] = bool(device.isClosed())
    except Exception as exc:
        record["closed"] = False
        record["errors"].append(f"close failed: {type(exc).__name__}: {exc}")


def preflight(dai, results, found):
    """Match every expectation to exactly one discovered device; return DeviceInfos, or None if any fail."""
    selected = []
    for r in results:
        ip, device_id = r["requested_ip"], r["expected_device_id"]
        at_ip = [i for i in found if getattr(i, "name", None) == ip]
        with_id = [i for i in found if device_id_of(i) == device_id]
        problems = []
        if len(at_ip) != 1:
            problems.append(f"{len(at_ip)} device(s) answered discovery at {ip}")
        if len(with_id) != 1:
            problems.append(f"{len(with_id)} device(s) reported ID {device_id}")
        if len(at_ip) == 1:
            seen_id = device_id_of(at_ip[0])
            r["preflight_seen_device_id"] = seen_id
            r["preflight_seen_state"] = str(at_ip[0].state)
            if seen_id != device_id:
                problems.append(f"{ip} reported ID {seen_id}, expected {device_id}")
            if at_ip[0].state != dai.XLinkDeviceState.X_LINK_BOOTLOADER:
                problems.append(f"{ip} is in state {at_ip[0].state}, expected X_LINK_BOOTLOADER "
                                "(in use by another host, or still running firmware from an earlier attempt)")
        r["preflight"] = "failed" if problems else "ok"
        r["errors"] += problems
        selected.append(None if problems else at_ip[0])
    return None if None in selected else selected


def run_expected(dai, args, report, non_isolated):
    """Verified mode: pre-check, connect and verify each expected camera, hold together, always close all."""
    results = [{"requested_ip": ip, "expected_device_id": device_id, "status": "not_attempted",
                "actual_device_id": None, "actual_ip": None, "errors": []} for ip, device_id in args.expect]
    report["expected"] = results

    if non_isolated and not args.allow_non_isolated:
        log.error("Verified mode refused: its pre-check uses broadcast discovery; disconnect from other networks.")
        for r in results:
            r["status"] = "refused_non_isolated_network"
        return 1

    t0 = time.monotonic()
    found = list(dai.Device.getAllAvailableDevices())
    report["broadcast_results"] = {"seconds": round(time.monotonic() - t0, 2), "devices": [to_jsonable(i) for i in found]}
    log.info("Pre-check: broadcast discovery found %d device(s)", len(found))
    for info in found:
        log.info("  name=%s id=%s state=%s", getattr(info, "name", "?"), device_id_of(info), getattr(info, "state", "?"))

    selected = preflight(dai, results, found)
    if selected is None:
        for r in results:
            r["status"] = "preflight_failed" if r["errors"] else "not_attempted_other_preflight_failed"
            for problem in r["errors"]:
                log.error("[%s] pre-check: %s", r["requested_ip"], problem)
        log.error("No camera was booted because the pre-check failed.")
        return 1

    opened = []
    try:
        for n, (r, info) in enumerate(zip(results, selected)):
            if n and args.stagger_seconds:
                time.sleep(args.stagger_seconds)
            log.info("[%s] connecting to %s ...", r["requested_ip"], r["expected_device_id"])
            t0 = time.monotonic()
            try:
                device = dai.Device(info)
            except Exception as exc:
                r["connect_seconds"] = round(time.monotonic() - t0, 2)
                r["status"] = "connect_failed"
                r["errors"].append(f"{type(exc).__name__}: {exc}")
                log.error("[%s] connection failed after %.1f s: %s", r["requested_ip"], r["connect_seconds"], r["errors"][-1])
                continue
            opened.append((r, device))
            r["connect_seconds"] = round(time.monotonic() - t0, 2)
            r["actual_device_id"] = device.getDeviceId()
            r["actual_ip"] = getattr(device.getDeviceInfo(), "name", None)
            if (r["actual_device_id"], r["actual_ip"]) != (r["expected_device_id"], r["requested_ip"]):
                r["status"] = "identity_mismatch"
                r["errors"].append(f"connected to {r['actual_device_id']} at {r['actual_ip']}, "
                                   f"expected {r['expected_device_id']} at {r['requested_ip']}")
                log.error("[%s] %s; closing it now", r["requested_ip"], r["errors"][-1])
                close_device(r, device)
                continue
            r["status"] = "connected_verified"
            r["product_name"] = safe_call(device, "getProductName")
            r["bootloader_version"] = safe_call(device, "getBootloaderVersion")
            log.info("[%s] verified %s (%s) in %.2f s", r["requested_ip"], r["actual_device_id"],
                     r["product_name"], r["connect_seconds"])

        live = [(r, d) for r, d in opened if r["status"] == "connected_verified"]
        report["concurrently_open_verified"] = len(live)
        if len(live) == len(results) and args.hold_seconds > 0:
            log.info("Holding %d verified connection(s) open together for %.0f s", len(live), args.hold_seconds)
            deadline = time.monotonic() + args.hold_seconds
            while time.monotonic() < deadline:
                for r, d in live:
                    if r["status"] != "connected_verified":
                        continue
                    try:
                        if d.isClosed():
                            raise RuntimeError("device connection closed during hold")
                        r.setdefault("hold_chip_temperature_c", []).append(round(d.getChipTemperature().average, 1))
                    except Exception as exc:
                        r["status"] = "failed_during_hold"
                        r["errors"].append(f"{type(exc).__name__}: {exc}")
                        log.error("[%s] %s", r["requested_ip"], r["errors"][-1])
                time.sleep(1.0)
        for r, _ in live:
            if r["status"] == "connected_verified":
                r["status"] = "verified_and_held" if len(live) == len(results) and args.hold_seconds > 0 else "verified"
    finally:
        for r, device in reversed(opened):
            close_device(r, device)

    ok_status = "verified_and_held" if args.hold_seconds > 0 else "verified"
    return 0 if all(r["status"] == ok_status and r.get("closed") for r in results) else 1


def summarise_expected(r):
    return [
        f"--- requested {r['requested_ip']} = {r['expected_device_id']} ---",
        f"  status         : {r['status']}",
        f"  actual         : {r['actual_device_id']} at {r['actual_ip']}",
        f"  connect time   : {r.get('connect_seconds')} s",
        f"  closed cleanly : {r.get('closed')}",
        f"  errors         : {r['errors'] or 'none'}",
    ]


def run_targets(dai, args, report, non_isolated, stamp):
    """Original modes: --broadcast, --ip, --no-connect and --simultaneous (IP-only identity)."""
    exit_code = 0
    targets = []
    if args.broadcast:
        if non_isolated and not args.allow_non_isolated:
            log.error("Broadcast discovery refused: disconnect from other networks first, or use --ip.")
            report["broadcast_results"] = "refused: non-isolated network"
            exit_code = 1
        else:
            t0 = time.monotonic()
            found = list(dai.Device.getAllAvailableDevices())
            elapsed = round(time.monotonic() - t0, 2)
            report["broadcast_results"] = {"seconds": elapsed, "devices": [to_jsonable(i) for i in found]}
            log.info("Broadcast discovery found %d device(s) in %.2f s", len(found), elapsed)
            for info in found:
                log.info("  name=%s id=%s state=%s", getattr(info, "name", "?"), device_id_of(info),
                         getattr(info, "state", "?"))
                targets.append((f"broadcast {getattr(info, 'name', device_id_of(info))}", info))

    seen_names = {getattr(info, "name", None) for _, info in targets}
    for ip in args.ip:
        if ip in seen_names:
            continue
        if not is_isolated_address(ip):
            log.warning("%s is not a link-local address; check it is on the isolated camera network.", ip)
        targets.append((f"ip {ip}", dai.DeviceInfo(ip)))

    if args.no_connect:
        for label, info in targets:
            report["devices"].append({"label": label, "device_info": to_jsonable(info), "connected": False})
    elif args.simultaneous:
        with contextlib.ExitStack() as stack:
            opened = []
            for label, info in targets:
                record = {"label": label, "device_info_before_connect": to_jsonable(info)}
                report["devices"].append(record)
                device = connect(dai, info, record)
                if device is not None:
                    stack.enter_context(device)
                    opened.append((record, device))
            report["simultaneously_connected"] = len(opened)
            log.info("Simultaneously connected: %d of %d", len(opened), len(targets))
            for record, device in opened:
                record.update(describe_connected(dai, device, stamp))
    else:
        for label, info in targets:
            record = {"label": label, "device_info_before_connect": to_jsonable(info)}
            report["devices"].append(record)
            device = connect(dai, info, record)
            if device is not None:
                with device:
                    record.update(describe_connected(dai, device, stamp))

    if any("error" in d for d in report["devices"]) or not report["devices"]:
        exit_code = 1
    return exit_code


def main():
    args = parse_args()
    # Restrict DepthAI to network devices; must be set before depthai is imported.
    os.environ.setdefault("DEPTHAI_PROTOCOL", "tcpip")
    os.environ.setdefault("DEPTHAI_CONNECT_TIMEOUT", str(args.connect_timeout_ms))

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = RESULTS_DIR / f"discover_{stamp}.log"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(log_path, encoding="utf-8")])

    addresses = host_ipv4_addresses()
    non_isolated = [a for a in addresses if not is_isolated_address(a)]
    report = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "hostname": socket.gethostname(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "host_ipv4": addresses,
        "args": vars(args),
        "broadcast_results": None,
        "devices": [],
    }
    log.info("Host IPv4 addresses: %s", addresses)
    if non_isolated:
        log.warning("Non-link-local addresses active (laptop is on another network): %s", non_isolated)

    exit_code = 0
    dumps_before = crash_dumps()
    try:
        import depthai as dai
        report["depthai_version"] = getattr(dai, "__version__", "unknown")
        report["depthai_commit"] = getattr(dai, "__commit__", "unknown")
        log.info("DepthAI %s", report["depthai_version"])

        if args.expect:
            exit_code = run_expected(dai, args, report, non_isolated)
        else:
            exit_code = run_targets(dai, args, report, non_isolated, stamp)
    except KeyboardInterrupt:
        log.warning("Interrupted by user.")
        exit_code = 130
    except Exception as exc:
        report["fatal_error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        log.error("Fatal error: %s", report["fatal_error"])
        exit_code = 1
    finally:
        report["new_crash_dumps"] = sorted(crash_dumps() - dumps_before)
        if report["new_crash_dumps"]:
            log.warning("DepthAI saved new crash dump(s): %s", report["new_crash_dumps"])
            if args.expect:
                exit_code = 1
        json_path = RESULTS_DIR / f"discover_{stamp}.json"
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        for record in report["devices"]:
            if record.get("connected") is False:
                continue
            for line in summarise(record):
                log.info(line)
        for r in report.get("expected", []):
            for line in summarise_expected(r):
                log.info(line)
        if args.expect:
            log.info("RESULT: %s", "PASS" if exit_code == 0 else "FAIL")
        log.info("Report: %s", json_path)
        log.info("Log   : %s", log_path)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
