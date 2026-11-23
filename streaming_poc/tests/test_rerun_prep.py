"""Offline checks for the G1-rerun preparation (analysis side; no processes, no network).

  * resources_summary: interpreter PIDs and system-wide CPU/memory are
    reported; G1-era evidence (no system.csv / pids.json) still summarises;
  * S8 stays strict with the new cleanup.json fields: a process recorded at
    the check FAILs S8 even if it was stopped afterwards;
  * the unchanged criterion code still scores the preserved G1 evidence as
    before (P2 FAIL at 1,647 ms on camera A, S8 FAIL). Functions are called
    directly, so nothing in the evidence folder is rewritten.

Run: .venv\\Scripts\\python.exe -I tests\\test_rerun_prep.py
"""
import hashlib
import json
import pathlib
import shutil
import sys
import tempfile

POC = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC))

import poc_common as pc  # noqa: E402
import smoke_check as sc  # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (("  -- " + str(detail)) if detail and not cond else ""))


tmp = pathlib.Path(tempfile.mkdtemp(prefix="rerun_prep_"))

# --- resources_summary with interpreter PIDs and system.csv -------------------
rows = ["t_s,utc,role,pid,cpu_total_s,working_set_mb,private_mb,threads,handles"]
for i in range(5):
    rows.append("{:.2f},x,pub_A,200,{:.3f},150.0,{:.1f},20,300".format(5.0 * i, 2.5 * i, 140 + i))   # 50 % of one core
    rows.append("{:.2f},x,mediamtx,100,{:.3f},40.0,60.0,30,400".format(5.0 * i, 1.0 * i))
(tmp / "resources.csv").write_text("\n".join(rows) + "\n")
srows = ["t_s,utc,cpu_busy_pct_all_cores,logical_cpus,mem_load_pct,mem_avail_mb,mem_total_mb", "0.00,x,,20,47,8000.0,16000.0"]
srows += ["{:.2f},x,{:.2f},20,48,7900.0,16000.0".format(5.0 * i, 10.0 + i) for i in range(1, 5)]
(tmp / "system.csv").write_text("\n".join(srows) + "\n")
(tmp / "pids.json").write_text(json.dumps([{"role": "pub_A", "launcher_pid": 199, "interpreter_pid": 200,
                                            "sampled": "interpreter (launcher child)",
                                            "interpreter_exe": "C:\\Python313\\python.exe"}]))
r = sc.resources_summary(tmp)
check("resources: per-process CPU % of one core from interpreter samples (50 %)",
      r["pub_A"]["cpu_pct_one_core"]["median"] == 50.0, r["pub_A"])
check("resources: CPU also normalised to all cores (50 / 20 = 2.5 %)",
      r["pub_A"]["cpu_pct_all_cores"]["median"] == 2.5, r["pub_A"].get("cpu_pct_all_cores"))
check("resources: sampled process recorded as the interpreter", r["pub_A"]["sampled"].startswith("interpreter"))
check("resources: system-wide CPU and memory summarised (first, baseline-only row skipped)",
      r["system"]["cpu_busy_pct_all_cores"]["n"] == 4 and r["system"]["cpu_busy_pct_all_cores"]["median"] == 12.5
      and r["system"]["logical_cpus"] == 20 and r["system"]["mem_load_pct"]["n"] == 5, r["system"])

# --- S8 strictness with the new cleanup fields --------------------------------
base = {"mediamtx_running": False, "port_8554_listening": False, "launch_blocked": False,
        "python_exit_wait": {"all_exited": True, "waited_s": 2.1, "timeout_s": 60, "still_running": []},
        "standby_events_during_run": []}
(tmp / "cleanup.json").write_text(json.dumps(dict(base, poc_python_pids=[], stopped_after_check=[])))
C, _ = sc.global_criteria(tmp, [])
check("S8: PASS when everything exited before the check", C["S8_processes_and_ports_closed"]["verdict"] == "PASS",
      C["S8_processes_and_ports_closed"])
(tmp / "cleanup.json").write_text(json.dumps(dict(base, poc_python_pids=[4242], stopped_after_check=[4242])))
C, _ = sc.global_criteria(tmp, [])
check("S8: FAIL when a process was still running at the check, even though stopped afterwards",
      C["S8_processes_and_ports_closed"]["verdict"] == "FAIL")

# --- preserved G1 evidence: same verdicts from the unchanged criterion code -----
G1 = POC / "results" / "smoke_20261105_122716"
pubA = POC / "results" / "pub_20261105_122722_A_g1_A"
digest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(G1.iterdir()) if p.is_file()}
r_old = sc.resources_summary(G1)
check("G1 evidence: resources summarise without system.csv / pids.json", r_old and "system" not in r_old
      and "pub_A" in r_old and "sampled" not in r_old["pub_A"])
C, _ = sc.global_criteria(G1, [])
check("G1 evidence: S8 still FAIL", C["S8_processes_and_ports_closed"]["verdict"] == "FAIL")
C = {}
sc.publisher_outage(C, {}, pubA, sc._json(pubA / "report.json"), sc._csv(pubA / "sent.csv"),
                    pc.read_events(pubA / "events.jsonl"), sc._json(G1 / "restart.json"))
p2 = C["P2_bounded_queue_no_stale_backlog"]
check("G1 evidence: P2 still FAIL at ~1,647 ms with the 200 ms limit (criterion unchanged)",
      p2["verdict"] == "FAIL" and abs(p2["first_frame_sent_after_recovery_age_ms"] - 1647) < 1 and p2["limit_ms"] == 200,
      p2)
after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(G1.iterdir()) if p.is_file()}
check("G1 evidence: no file in the evidence folder changed by these checks", after == digest)

shutil.rmtree(tmp, ignore_errors=True)
print()
n_fail = sum(1 for _, ok in RESULTS if not ok)
print("{} checks, {} failed".format(len(RESULTS), n_fail))
sys.exit(1 if n_fail else 0)
