"""Offline tests for S7b v2 (smoke_check.s7b_v2) and for S7b v1 staying unchanged.

  * synthetic cases: burst stall with arrivals and a rejection in the window
    (PASS); drop stall with no held arrival and no rejection (rejection "not
    applicable", PASS); held frames arrived but the only rejection is outside the
    window (FAIL); a rejection of an unrelated frame inside the window (FAIL);
    3 held frames shown (FAIL); recovery not at the first frame (FAIL); a
    displayed pair over the threshold (FAIL); safeguard off (NOT_TESTED).
  * recorded evidence (read-only, nothing written): the G1 rerun keeps its v1
    verdict FAIL exactly as recorded in its smoke_report.json; v2 is computed as a
    separate key (test fixture only, not a verdict on that run); no evidence file
    changes.

Run: .venv\\Scripts\\python.exe -I tests\\test_s7b_v2.py
"""
import hashlib
import json
import pathlib
import sys

POC = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POC))

import smoke_check as sc  # noqa: E402

RESULTS = []
S = 10**9


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (("  -- " + str(detail)) if detail and not cond else ""))


def case(mode="burst", arrived=True, rej_at=2.5, rej_seq=41, shown=(), recover=0, over=(), enabled=True):
    """One stall: seq 40-53 held from t=2.0 s to t=2.7 s (end)."""
    stalls = [{"start_ns": 2 * S, "end_ns": int(2.7 * S), "seq_first": 40, "seq_last": 53, "mode": mode}]
    s7 = [{"first_display_after": {"seq": 55}, "frames_to_recover_age": recover}]
    ok_arr = ([{"seq": str(q), "t_arrival_utc_ns": str(int(2.75 * S) + q)} for q in range(40, 54)] if arrived else [])
    frames = [{"seq": str(q), "t_display_utc_ns": str(int(2.8 * S) + q)} for q in list(shown) + [55, 56]]
    rejects = [] if rej_at is None else [{"t_utc_ns": int(rej_at * S), "payload": {"seq": rej_seq, "obsolete_older": []}}]
    dseq = [int(f["seq"]) for f in frames]
    return sc.s7b_v2(stalls, s7, frames, ok_arr, rejects, {"enabled": enabled}, list(over), [],
                     all(b > a for a, b in zip(dseq, dseq[1:])), dseq, 100.0)


r = case()
check("burst stall, held frames arrived, rejection in window -> PASS", r["verdict"] == "PASS", r)
check("v2 result carries version 2 and the 2 s window", r["version"] == 2 and r["window_after_stall_end_s"] == 2.0)
r = case(mode="drop", arrived=False, rej_at=None)
check("drop stall, no held frame arrived, no rejection -> rejection not applicable, PASS",
      r["verdict"] == "PASS" and r["stalls"][0]["rejection_requirement"].startswith("not applicable"), r)
r = case(rej_at=4.8)
check("held frames arrived, only rejection 2.1 s after the stall end -> FAIL", r["verdict"] == "FAIL", r)
r = case(rej_at=2.5, rej_seq=200)
check("rejection in window but of an unrelated frame -> FAIL", r["verdict"] == "FAIL", r)
r = sc.s7b_v2([{"start_ns": 2 * S, "end_ns": int(2.7 * S), "seq_first": 40, "seq_last": 53, "mode": "burst"}],
              [{"first_display_after": {"seq": 55}, "frames_to_recover_age": 0}],
              [{"seq": "55", "t_display_utc_ns": str(3 * S)}],
              [{"seq": "45", "t_arrival_utc_ns": str(int(2.75 * S))}],
              [{"t_utc_ns": int(2.9 * S), "payload": {"seq": 60, "obsolete_older": [44, 45]}}],
              {"enabled": True}, [], [], True, [55], 100.0)
check("held frame rejected as obsolete backlog of a later rejection (in window) -> PASS", r["verdict"] == "PASS", r)
r = case(shown=(50, 51, 52))
check("3 held frames shown -> FAIL", r["verdict"] == "FAIL", r)
r = case(shown=(52, 53))
check("2 held frames shown -> PASS (limit <= 2)", r["verdict"] == "PASS", r)
r = case(recover=1)
check("recovery not at the first frame after the stall -> FAIL", r["verdict"] == "FAIL", r)
r = case(over=[{"excess_ms": "150"}])
check("a displayed pair over the excess threshold -> FAIL", r["verdict"] == "FAIL", r)
r = case(enabled=False)
check("freshness safeguard off -> NOT_TESTED", r["verdict"] == "NOT_TESTED", r)

# --- recorded evidence: v1 unchanged, v2 separate; nothing written ----------------
G1R = POC / "results" / "smoke_20261105_151122"
pub, rx = POC / "results" / "pub_20261105_151130_A_g1r_A", POC / "results" / "rx_20261105_151132_A_g1r_A"
if G1R.exists():
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for d in (G1R, pub, rx) for p in d.rglob("*") if p.is_file()}
    recorded = json.loads((G1R / "smoke_report.json").read_text(encoding="utf-8"))
    rec_v1 = next(v for k, v in recorded["streams"].items() if k.startswith("A:"))["criteria"]["S7b_stale_frame_rejection"]
    C, _M = sc.stream_analysis(pub, rx, sc.mediamtx_text(G1R), json.loads((G1R / "restart.json").read_text(encoding="utf-8-sig")))
    check("G1 rerun camera A: S7b v1 recomputed = recorded verdict FAIL (v1 unchanged)",
          C["S7b_stale_frame_rejection"]["verdict"] == rec_v1["verdict"] == "FAIL",
          (C["S7b_stale_frame_rejection"]["verdict"], rec_v1["verdict"]))
    check("G1 rerun: v1 per-stall details identical to the recorded report",
          [x["rejection_events"] for x in C["S7b_stale_frame_rejection"]["stalls"]] == [x["rejection_events"] for x in rec_v1["stalls"]])
    v2 = C["S7b_v2_stale_frame_rejection"]
    check("G1 rerun: v2 reported under its own key; its drop stall is 'not applicable' (fixture, not a verdict)",
          v2["version"] == 2 and v2["stalls"][2]["rejection_requirement"].startswith("not applicable"), v2["stalls"][2])
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for d in (G1R, pub, rx) for p in d.rglob("*") if p.is_file()}
    check("G1 rerun evidence unchanged (no file written or modified)", before == after)

print()
n_fail = sum(1 for _, ok in RESULTS if not ok)
print("{} checks, {} failed".format(len(RESULTS), n_fail))
sys.exit(1 if n_fail else 0)
