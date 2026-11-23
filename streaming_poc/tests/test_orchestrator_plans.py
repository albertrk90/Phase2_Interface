"""Offline regression tests for run_smoke_restart.ps1 (orchestrator v3). Uses only
-PlanOnly and -SelfTest: nothing is launched, no port is opened.

  * the default two-camera plan with the G1 rerun parameters reproduces exactly
    the arguments the G1 rerun processes recorded (defaults unchanged);
  * -Cameras A -NoRestart with the T3 parameters reproduces exactly what the T3
    smoke processes recorded;
  * the proposed T4 plan: camera A only, restart at 300 s (down 5 s), the
    compressed G1 faults, publisher 400 s, receiver cap 500 s, external process;
  * invalid -Cameras is refused; -SelfTest passes (incl. external-process
    tracking and the [] serialisation).

Run: .venv\\Scripts\\python.exe -I tests\\test_orchestrator_plans.py
"""
import json
import ntpath
import pathlib
import subprocess
import sys
import tempfile

POC = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC))
import poc_common as pc  # noqa: E402

RESULTS = []
TMP = tempfile.mkdtemp(prefix="orch_plan_")
T4 = ["-Cameras", "A", "-Seconds", "400", "-Stall", "60:300:burst,120:700:burst,180:700:drop", "-Drop", "240:5",
      "-RestartAt", "300", "-DownSeconds", "5", "-Label", "m1t4", "-ExternalProcess", "Phase2M1", "-ExitWaitSeconds", "60"]


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (("  -- " + str(detail)) if detail and not cond else ""))


def ps(args):
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(POC / "run_smoke_restart.ps1")]
                       + args + ["-SelfTestDir", TMP], capture_output=True, text=True, timeout=180)
    return r.returncode, r.stdout, r.stderr


def plan(args):
    rc, out, err = ps(["-PlanOnly"] + args)
    return json.loads(out) if rc == 0 else {"error": err, "rc": rc}


def norm(a):
    return [("<control>/" + ntpath.basename(x)) if x.endswith(".done") else x for x in a]


def recorded_argv(folder):
    return next(e for e in pc.read_events(POC / "results" / folder / "events.jsonl") if e["type"] == "run_start")["payload"]["argv"]


p = plan(["-Seconds", "660", "-Stall", "120:300:burst,240:700:burst,360:700:drop", "-Drop", "480:5",
          "-RestartAt", "540", "-DownSeconds", "5", "-Label", "g1r"])
rec = {"pub_A": "pub_20261105_151130_A_g1r_A", "pub_B": "pub_20261105_151130_B_g1r_B",
       "rx_A": "rx_20261105_151132_A_g1r_A", "rx_B": "rx_20261105_151132_B_g1r_B"}
check("default plan: cameras A,B, restart enabled, 4 roles", p.get("cameras") == ["A", "B"] and p.get("restart", "").startswith("at 540")
      and [l["role"] for l in p["launches"]] == ["pub_A", "pub_B", "rx_A", "rx_B"], p)
for l in p.get("launches", []):
    check("default plan {}: identical to the recorded G1-rerun arguments".format(l["role"]),
          norm(l["args"]) == norm(recorded_argv(rec[l["role"]])))

p = plan(["-Cameras", "A", "-NoRestart", "-Seconds", "100", "-Stall", "none", "-Label", "m1t3", "-ExternalProcess", "Phase2M1"])
rec3 = {"pub_A": "pub_20261105_170124_A_m1t3_A", "rx_A": "rx_20261105_170125_A_m1t3_A"}
check("T3 plan: camera A only, restart disabled", p.get("cameras") == ["A"] and p.get("restart") == "disabled"
      and [l["role"] for l in p["launches"]] == ["pub_A", "rx_A"], p)
for l in p.get("launches", []):
    check("T3 plan {}: identical to the recorded T3 arguments".format(l["role"]), norm(l["args"]) == norm(recorded_argv(rec3[l["role"]])))

p = plan(T4)
pub = next(l for l in p["launches"] if l["role"] == "pub_A")
rx = next(l for l in p["launches"] if l["role"] == "rx_A")
a = pub["args"]
check("T4 plan: camera A only, restart at 300 s down 5 s, external Phase2M1",
      p["cameras"] == ["A"] and p["restart"] == "at 300 s, down 5 s" and p["external_process"] == "Phase2M1"
      and [l["role"] for l in p["launches"]] == ["pub_A", "rx_A"], p)
check("T4 plan: publisher 400 s, end-of-frame SEI, the 3 stalls and the 5-frame drop",
      a[a.index("--seconds") + 1] == "400" and a[a.index("--frame-end") + 1] == "sei"
      and [a[i + 1] for i, x in enumerate(a) if x == "--stall"] == ["60:300:burst", "120:700:burst", "180:700:drop"]
      and [a[i + 1] for i, x in enumerate(a) if x == "--drop"] == ["240:5"], a)
check("T4 plan: Python reference receiver cap 500 s, freshness defaults, frames saved every 200",
      rx["args"][rx["args"].index("--seconds") + 1] == "500" and "--save-every" in rx["args"] and "--freshness" not in rx["args"], rx["args"])

rc, out, err = ps(["-PlanOnly", "-Cameras", "C"])
check("-Cameras C refused (non-zero exit, message)", rc != 0 and "-Cameras accepts A and/or B" in (out + err), (rc, err[-200:]))
rc, out, err = ps(["-SelfTest"])
check("-SelfTest PASS (v3: external-process tracking, [] serialisation, camera options)",
      rc == 0 and "SELFTEST PASS" in out and "external process found by name" in out, out[-400:])

print()
n_fail = sum(1 for _, ok in RESULTS if not ok)
print("{} checks, {} failed".format(len(RESULTS), n_fail))
sys.exit(1 if n_fail else 0)
