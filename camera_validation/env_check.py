"""Record the Python / DepthAI / OpenCV / NumPy environment and check API availability.

Does not search for or connect to any camera, so it is safe to run on any network.

    .venv\\Scripts\\python.exe env_check.py
"""

import datetime as dt
import json
import platform
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent / "results"

# Attributes the Task 03 scripts rely on (DepthAI v3 names), plus v2-only names for reference.
EXPECTED_API = {
    "dai": ["Device", "DeviceInfo", "Pipeline", "CameraBoardSocket", "ImgFrame", "MessageGroup",
            "CalibrationHandler", "XLinkDeviceState", "XLinkProtocol"],
    "dai.node": ["Camera", "StereoDepth", "Sync", "MonoCamera", "XLinkOut"],
    "dai.Device": ["getAllAvailableDevices", "getDeviceInfo", "getDeviceId", "getDeviceName",
                   "getProductName", "getBootloaderVersion", "getConnectedCameras",
                   "getConnectedCameraFeatures", "getCameraSensorNames", "getIrDrivers",
                   "readCalibration", "readCalibration2", "readFactoryCalibration",
                   "setIrLaserDotProjectorIntensity", "setIrFloodLightIntensity"],
    "dai.CalibrationHandler": ["eepromToJson", "getEepromData", "getBaselineDistance",
                               "getCameraIntrinsics", "getDistortionCoefficients",
                               "getCameraExtrinsics", "getStereoLeftRectificationRotation",
                               "getStereoRightRectificationRotation"],
}


def main():
    report = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "python": sys.version,
        "executable": sys.executable,
        "in_virtualenv": sys.prefix != sys.base_prefix,
        "platform": platform.platform(),
        "packages": {},
        "api": {},
    }

    for module_name in ("numpy", "cv2", "depthai"):
        try:
            module = __import__(module_name)
            report["packages"][module_name] = getattr(module, "__version__", "unknown")
        except Exception as exc:
            report["packages"][module_name] = f"IMPORT FAILED: {type(exc).__name__}: {exc}"

    try:
        import depthai as dai
        report["packages"]["depthai_commit"] = getattr(dai, "__commit__", "unknown")
        roots = {"dai": dai, "dai.node": getattr(dai, "node", None),
                 "dai.Device": getattr(dai, "Device", None),
                 "dai.CalibrationHandler": getattr(dai, "CalibrationHandler", None)}
        for root_name, names in EXPECTED_API.items():
            root = roots[root_name]
            report["api"][root_name] = {name: root is not None and hasattr(root, name) for name in names}
    except ImportError:
        pass

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / f"env_check_{dt.datetime.now():%Y%m%d_%H%M%S}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Python      : {sys.version.split()[0]}  ({sys.executable})")
    print(f"In venv     : {report['in_virtualenv']}")
    for name, version in report["packages"].items():
        print(f"{name:<12}: {version}")
    for root_name, checks in report["api"].items():
        missing = [name for name, present in checks.items() if not present]
        print(f"{root_name:<12}: {len(checks) - len(missing)}/{len(checks)} present"
              + (f"; missing: {', '.join(missing)}" if missing else ""))
    print(f"Saved       : {out_path}")


if __name__ == "__main__":
    main()
