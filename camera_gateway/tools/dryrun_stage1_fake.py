"""Offline dry run of the Stage 1 flow on the FAKE DepthAI device (no camera, no network).

camera_gateway_a.run() with exactly the Stage 1 arguments (--sink file --seconds 30
--dump-raw), real Camera A imagery through the libx264 stand-in, written like a
live run (gw_<stamp>_A_<label>/ with report.json), so run_stage1.ps1 -DryRun and
analyse_stage1.py can be exercised end to end before the hardware session.
Run: camera_gateway\\.venv\\Scripts\\python.exe -I camera_gateway\\tools\\dryrun_stage1_fake.py [--label stage1dry]
"""
import argparse
import datetime as dt
import json
import pathlib
import sys

sys.dont_write_bytecode = True
GW = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(GW), str(GW / "tools"), str(GW / "tests")]

import camera_gateway_a as cga  # noqa: E402
import fake_dai  # noqa: E402
import standin_encoder as se  # noqa: E402

R = GW.parent / "camera_validation" / "results"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="stage1dry")
    ap.add_argument("--fault", choices=("none", "bootloader", "gap"), default="none",
                    help="designed-to-fail dry runs: a non-validated bootloader, or a 40-frame device gap")
    a = ap.parse_args(argv)
    pairs = se.load_e1_pairs()
    n = 660
    aul = se.encode_sequence([pairs[k % 5][1] for k in range(n)], keyint=20)
    aur = se.encode_sequence([pairs[k % 5][2] for k in range(n)], keyint=20)
    calls = []
    user = json.loads((R / "calibration_user_19443010B14C872F00_20261103_182445.json").read_text(encoding="utf-8"))
    factory = json.loads((R / "calibration_factory_19443010B14C872F00_20261103_182445.json").read_text(encoding="utf-8"))
    fault = {"bootloader": {"bootloader": "0.0.29"}, "gap": {"skip_seqs": set(range(300, 340))}}.get(a.fault, {})
    fake, _u, _f = fake_dai.make_fake_dai(calls, aul, aur, autocal_sticks=False, frames=n, calib_user=user, calib_factory=factory, **fault)
    cs, cc, dc = cga.load_safety_modules()
    args = cga.parse_args(["--expect", "169.254.1.222=19443010B14C872F00",
                           "--baseline-user", str(R / "calibration_user_19443010B14C872F00_20261103_182445.json"),
                           "--baseline-factory", str(R / "calibration_factory_19443010B14C872F00_20261103_182445.json"),
                           "--live", "--sink", "file", "--seconds", "30", "--label", a.label, "--dump-raw",
                           "--post-verify-wait-s", "5"], dc)
    args.allow_non_isolated = True          # FAKE ONLY: this laptop is on Wi-Fi; the live run never sets this
    out = cga.RESULTS / "gw_{}_A_{}".format(dt.datetime.now().strftime("%Y%m%d_%H%M%S"), a.label)
    out.mkdir(parents=True)
    rep = {"tool": "dryrun_stage1_fake.py (FAKE DEVICE)", "fake_device": True, "fault": a.fault}
    code = cga.run(fake, args, out, rep, cs, cc, dc)
    rep["exit_code"] = code
    rep["forbidden_calls"] = [c for c in calls if c.startswith("FORBIDDEN")]
    (out / "report.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print("RESULT: {} (FAKE) -> {}".format("PASS" if code == 0 else "FAIL", out))
    return code


if __name__ == "__main__":
    sys.exit(main())
