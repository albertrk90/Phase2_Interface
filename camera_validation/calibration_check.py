"""Read-only calibration verification for one OAK PoE camera (DepthAI v3).

Connects with the Stage B verified method (broadcast pre-check, then device-ID
and IP check), reads the user and factory calibration, compares them by content
(the parsed calibration data, not just a successful API call), optionally against
saved baseline copies, and always closes the device. No pipeline is created, so
DepthAI's pipeline-level automatic calibration cannot run, and the IR stays off.
Nothing is written to the camera.

The module is also used by capture_stereo.py to re-check calibration after a
capture: DepthAI 3.11.0's Pipeline.stop() closes the device, so the calibration
is re-read through a fresh read-only connection once the camera is back in
bootloader state.

    .venv\\Scripts\\python.exe calibration_check.py --expect 169.254.1.222=19443010B14C872F00 ^
        --baseline-user results\\calibration_user_19443010B14C872F00_20261103_182445.json ^
        --baseline-factory results\\calibration_factory_19443010B14C872F00_20261103_182445.json
"""

import argparse
import datetime as dt
import hashlib
import json
import logging
import os
import socket
import sys
import time
import traceback
from pathlib import Path

import discover_cameras as dc

log = logging.getLogger("calibration")


def canonical(data):
    """JSON-normalised calibration data and its SHA-256 (hash is for the record; comparison uses the data)."""
    data = json.loads(json.dumps(dc.to_jsonable(data), sort_keys=True))
    return data, hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


def diff_paths(a, b, path="", limit=20):
    """List JSON paths where two calibration structures differ (at most `limit`)."""
    out = []

    def walk(x, y, p):
        if len(out) >= limit:
            return
        if type(x) is not type(y):
            out.append(f"{p or '/'}: type {type(x).__name__} != {type(y).__name__}")
        elif isinstance(x, dict):
            for k in sorted(set(x) | set(y)):
                if k not in x or k not in y:
                    out.append(f"{p}/{k}: present only in {'second' if k not in x else 'first'}")
                else:
                    walk(x[k], y[k], f"{p}/{k}")
        elif isinstance(x, list):
            if len(x) != len(y):
                out.append(f"{p or '/'}: length {len(x)} != {len(y)}")
            for i, (u, v) in enumerate(zip(x, y)):
                walk(u, v, f"{p}[{i}]")
        elif x != y:
            out.append(f"{p or '/'}: {x!r} != {y!r}")

    walk(a, b, path)
    return out


def comparison(name_a, a, name_b, b):
    diffs = diff_paths(a, b)
    return {"compared": f"{name_a} vs {name_b}", "equal": a == b, "differences": diffs}


def read_user_and_factory(device):
    """Read both calibrations from an open device. Raises if either cannot be read."""
    user, user_hash = canonical(device.readCalibration().eepromToJson())
    factory, factory_hash = canonical(device.readFactoryCalibration().eepromToJson())
    if not user.get("cameraData"):
        raise RuntimeError("user calibration returned no cameraData")
    return {"user": user, "user_sha256": user_hash, "factory": factory, "factory_sha256": factory_hash}


def load_baseline(path):
    data, digest = canonical(json.loads(Path(path).read_text(encoding="utf-8")))
    return {"path": str(path), "data": data, "sha256": digest}


def reconnect_and_read(dai, expect, allow_non_isolated, wait_s=60.0, poll_s=2.0):
    """Wait for the camera to return to bootloader state, connect (verified), read calibration, always close.

    Returns a record: status, attempts, timings, errors, and the calibration data on success.
    """
    ip, device_id = expect
    rec = {"requested_ip": ip, "expected_device_id": device_id, "status": "not_attempted",
           "errors": [], "precheck_attempts": 0}
    non_isolated = [a for a in dc.host_ipv4_addresses() if not dc.is_isolated_address(a)]
    if non_isolated and not allow_non_isolated:
        rec["status"] = "refused_non_isolated_network"
        rec["errors"].append(f"non-link-local addresses active {non_isolated}")
        return rec
    t0 = time.monotonic()
    selected = None
    while True:
        rec["precheck_attempts"] += 1
        probe = {"requested_ip": ip, "expected_device_id": device_id, "errors": []}
        try:
            found = list(dai.Device.getAllAvailableDevices())
        except Exception as exc:
            rec["status"] = "error"
            rec["errors"].append(f"discovery failed: {type(exc).__name__}: {exc}")
            return rec
        selected = dc.preflight(dai, [probe], found)
        rec["last_precheck"] = {"errors": probe["errors"], "seen_state": probe.get("preflight_seen_state")}
        if selected is not None or time.monotonic() - t0 >= wait_s:
            break
        time.sleep(poll_s)
    rec["waited_s"] = round(time.monotonic() - t0, 2)
    if selected is None:
        rec["status"] = "camera_not_back_in_bootloader"
        rec["errors"].append(f"pre-check still failing after {rec['waited_s']} s: {probe['errors']}")
        return rec

    device = None
    try:
        t1 = time.monotonic()
        device = dai.Device(selected[0])
        rec["connect_seconds"] = round(time.monotonic() - t1, 2)
        rec["actual_device_id"] = device.getDeviceId()
        rec["actual_ip"] = getattr(device.getDeviceInfo(), "name", None)
        if (rec["actual_device_id"], rec["actual_ip"]) != (device_id, ip):
            rec["status"] = "identity_mismatch"
            rec["errors"].append(f"connected to {rec['actual_device_id']} at {rec['actual_ip']}")
            return rec
        rec.update(read_user_and_factory(device))
        rec["status"] = "read_ok"
    except Exception as exc:
        rec["status"] = rec["status"] if rec["status"] == "identity_mismatch" else "error"
        rec["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        if device is not None:
            try:
                device.close()
                rec["device_closed"] = bool(device.isClosed())
            except Exception as exc:
                rec["device_closed"] = False
                rec["errors"].append(f"device.close failed: {type(exc).__name__}: {exc}")
    return rec


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--expect", required=True, metavar="IP=DEVICE_ID")
    parser.add_argument("--baseline-user", type=Path, help="saved user calibration JSON to compare against")
    parser.add_argument("--baseline-factory", type=Path, help="saved factory calibration JSON to compare against")
    parser.add_argument("--wait-s", type=float, default=60.0, help="how long to wait for bootloader state (5-180)")
    parser.add_argument("--allow-non-isolated", action="store_true")
    parser.add_argument("--connect-timeout-ms", type=int, default=15000)
    args = parser.parse_args(argv)
    args.expect = dc.parse_expectation(parser, args.expect)
    if not 5 <= args.wait_s <= 180:
        parser.error("--wait-s must be 5-180")
    if not (args.baseline_user or args.baseline_factory):
        parser.error("give --baseline-user and/or --baseline-factory")
    for p in (args.baseline_user, args.baseline_factory):
        if p is not None and not p.is_file():
            parser.error(f"baseline file not found: {p}")
    return args


def main(argv=None):
    args = parse_args(argv)
    os.environ.setdefault("DEPTHAI_PROTOCOL", "tcpip")
    os.environ.setdefault("DEPTHAI_CONNECT_TIMEOUT", str(args.connect_timeout_ms))
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = dc.RESULTS_DIR / f"calibration_check_{stamp}_{args.expect[1]}"
    out_dir.mkdir(parents=True, exist_ok=False)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(out_dir / "calibration_check.log", encoding="utf-8")])
    report = {"timestamp": dt.datetime.now().isoformat(timespec="seconds"), "hostname": socket.gethostname(),
              "args": {k: (str(v) if isinstance(v, Path) else list(v) if isinstance(v, tuple) else v)
                       for k, v in vars(args).items()}}
    dumps_before = dc.crash_dumps()
    exit_code = 1
    try:
        import depthai as dai
        report["depthai_version"] = getattr(dai, "__version__", "unknown")
        rec = reconnect_and_read(dai, args.expect, args.allow_non_isolated, wait_s=args.wait_s)
        report["read"] = {k: v for k, v in rec.items() if k not in ("user", "factory")}
        comparisons = []
        if rec["status"] == "read_ok":
            (out_dir / "calibration_user.json").write_text(json.dumps(rec["user"], indent=2), encoding="utf-8")
            (out_dir / "calibration_factory.json").write_text(json.dumps(rec["factory"], indent=2), encoding="utf-8")
            report["user_equals_factory"] = comparison("user", rec["user"], "factory", rec["factory"])
            for kind, path in (("user", args.baseline_user), ("factory", args.baseline_factory)):
                if path is not None:
                    base = load_baseline(path)
                    c = comparison(f"current {kind}", rec[kind], f"baseline {path.name}", base["data"])
                    c["baseline_sha256"] = base["sha256"]
                    comparisons.append(c)
        report["baseline_comparisons"] = comparisons
        passed = (rec["status"] == "read_ok" and rec.get("device_closed") is True
                  and comparisons and all(c["equal"] for c in comparisons))
        exit_code = 0 if passed else 1
    except Exception as exc:
        report["fatal_error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
    finally:
        report["new_crash_dumps"] = sorted(dc.crash_dumps() - dumps_before)
        if report["new_crash_dumps"]:
            exit_code = 1
        report["result"] = "PASS" if exit_code == 0 else "FAIL"
        (out_dir / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        read = report.get("read", {})
        log.info("Read: %s | device closed: %s | errors: %s", read.get("status"), read.get("device_closed"),
                 read.get("errors") or report.get("fatal_error") or "none")
        if "user_equals_factory" in report:
            log.info("user == factory: %s", report["user_equals_factory"]["equal"])
        for c in report.get("baseline_comparisons", []):
            log.info("%s: equal=%s %s", c["compared"], c["equal"], c["differences"][:5] or "")
        log.info("RESULT: %s  (%s)", report["result"], out_dir)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
