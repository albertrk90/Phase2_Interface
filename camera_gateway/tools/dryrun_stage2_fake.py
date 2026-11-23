"""OFFLINE Stage 2 dry run of the gateway on the FAKE DepthAI device (no camera, no MediaMTX).

camera_gateway_a.run() with the Stage 2 arguments (--seconds 120, --stop-file, the
same safeguards) and a NULL output in place of RTSP (there is no server in a dry run;
connect/write succeed and discard the data, so sent.csv, events and timing are real).
Writes camera_gateway/results/gw_<stamp>_A_<label>/ with report.json like a live run.

--fault bootloader : the fake device reports bootloader 0.0.29 -> the gateway refuses
                     before streaming (the runner must then never launch Unity).
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
import gateway_core as gc  # noqa: E402
import standin_encoder as se  # noqa: E402

R = GW.parent / "camera_validation" / "results"


class NullOutput:
    def __init__(self):
        self.writes = 0

    def connect(self, au, ps):
        gc.inspect_au(au)

    def write(self, au, seq, key):
        self.writes += 1
        return len(au)

    def close(self):
        pass


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="stage2dry")
    ap.add_argument("--stop-file", required=True)
    ap.add_argument("--seconds", default="120")
    ap.add_argument("--fault", choices=("none", "bootloader"), default="none")
    ap.add_argument("--extended-test", action="store_true")
    a = ap.parse_args(argv)
    pairs = se.load_e1_pairs()
    aul = se.encode_sequence([pairs[k % 5][1] for k in range(40)], keyint=20)
    aur = se.encode_sequence([pairs[k % 5][2] for k in range(40)], keyint=20)
    user = json.loads((R / "calibration_user_19443010B14C872F00_20261103_182445.json").read_text(encoding="utf-8"))
    factory = json.loads((R / "calibration_factory_19443010B14C872F00_20261103_182445.json").read_text(encoding="utf-8"))
    calls = []
    fake, _u, _f = fake_dai.make_fake_dai(calls, aul, aur, autocal_sticks=False, frames=int(float(a.seconds) * 20) + 400,
                                          calib_user=user, calib_factory=factory,
                                          **({"bootloader": "0.0.29"} if a.fault == "bootloader" else {}))
    cs, cc, dc = cga.load_safety_modules()
    args = cga.parse_args(["--expect", "169.254.1.222=19443010B14C872F00",
                           "--baseline-user", str(R / "calibration_user_19443010B14C872F00_20261103_182445.json"),
                           "--baseline-factory", str(R / "calibration_factory_19443010B14C872F00_20261103_182445.json"),
                           "--live", "--sink", "rtsp", "--seconds", a.seconds, "--label", a.label, "--stop-file", a.stop_file,
                           "--post-verify-wait-s", "5"] + (["--extended-test"] if a.extended_test else []), dc)

    args.allow_non_isolated = True          # FAKE ONLY: the live run never sets this
    out = cga.RESULTS / "gw_{}_A_{}".format(dt.datetime.now().strftime("%Y%m%d_%H%M%S"), a.label)
    out.mkdir(parents=True)
    print("GATEWAY_DIR", out, flush=True)
    rep = {"tool": "dryrun_stage2_fake.py (FAKE DEVICE, NULL OUTPUT)", "fake_device": True, "fault": a.fault}
    code = cga.run(fake, args, out, rep, cs, cc, dc, make_output=lambda eye, seg: NullOutput())
    rep["exit_code"] = code
    rep["forbidden_calls"] = [c for c in calls if c.startswith("FORBIDDEN")]
    (out / "report.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print("RESULT: {} (FAKE) stop {} -> {}".format("PASS" if code == 0 else "FAIL", rep.get("stop_reason"), out), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
