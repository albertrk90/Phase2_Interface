"""Re-analyse a recorded S4 session's inactive-location count with the corrected rule (13 Nov 2026, checkpoint §13.34):
each predefined inactive location counts ONCE per trial instance, whether reached at its autonomous release, by an unscheduled hold
served there, or both. Reads the raw session_events.jsonl only; writes a separate JSON next to it in <out_dir>; changes nothing.
Usage: reanalyse_inactive_locations.py <session_dir> <out_dir>"""
import json, pathlib, sys
sess, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
ev = [json.loads(l) for l in open(sess / "session_events.jsonl", encoding="utf-8")]
trials, cur = {}, None
for e in ev:
    p, ids = e.get("payload") or {}, e.get("ids") or {}
    if e["type"] == "trial_start":
        cur = p["trial"]["uid"]; trials[cur] = {"purpose": p["trial"]["purpose"], "autonomous": [], "holds": [], "recorded_count": None, "status": None}
    elif cur and e["type"] == "inactive_location":
        trials[cur]["autonomous"].append({"seq": e["seq"], "location": p.get("location"), "gt_ref": p.get("gt_ref")})
    elif cur and e["type"] == "unscheduled_episode_open" and ids.get("cdp_role") == "inactive":
        trials[cur]["holds"].append({"seq": e["seq"], "location": ids.get("cdp_location"), "episode": ids.get("episode_id")})
    elif e["type"] == "trial_end":
        uid = p["trial"]["uid"]
        trials[uid]["recorded_count"] = p.get("inactive_locations"); trials[uid]["status"] = p.get("status")
integ = next((e["payload"] for e in reversed(ev) if e["type"] == "integrity_checks"), {})
rows = []
for uid, t in trials.items():
    locs = sorted({x["location"] for x in t["autonomous"] + t["holds"] if x["location"]})
    links = [{"location": h["location"], "hold_episode": h["episode"], "hold_seq": h["seq"],
              "autonomous_seq": next((a["seq"] for a in t["autonomous"] if a["location"] == h["location"]), None)} for h in t["holds"]]
    for l in links: l["first_reached_by"] = "autonomous_release" if l["autonomous_seq"] is not None and l["autonomous_seq"] < l["hold_seq"] else "unscheduled_hold"
    rows.append({"trial": uid, "purpose": t["purpose"], "status": t["status"], "recorded_count_old_rule": t["recorded_count"],
                 "autonomous_records": len(t["autonomous"]), "unscheduled_holds_at_inactive": len(t["holds"]),
                 "distinct_inactive_locations_new_rule": len(locs), "locations": locs, "links": links})
measured = [r for r in rows if r["purpose"] == "measured" and r["status"] == "completed"]
old_check = next((c for c in integ.get("checks", []) if c["name"] == "inactive_locations"), None)
res = {
    "session": str(sess), "rule": "each predefined inactive location once per trial instance (autonomous release and later hold linked, both kept)",
    "trials": rows,
    "measured_completed": len(measured), "expected_inactive_total": len(measured) * 1,
    "old_rule_total": sum(r["recorded_count_old_rule"] or 0 for r in measured), "new_rule_total": sum(r["distinct_inactive_locations_new_rule"] for r in measured),
    "recorded_integrity_check": old_check,
    "other_integrity_checks_failed": [c["name"] for c in integ.get("checks", []) if not c["pass"] and c["name"] != "inactive_locations"],
}
res["inactive_locations_check_new_rule"] = res["new_rule_total"] == res["expected_inactive_total"]
res["integrity_fully_explained"] = (old_check is not None and not old_check["pass"] and res["inactive_locations_check_new_rule"] and not res["other_integrity_checks_failed"])
(out / "inactive_location_reanalysis.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
print(json.dumps({k: res[k] for k in ("old_rule_total", "new_rule_total", "expected_inactive_total", "inactive_locations_check_new_rule", "other_integrity_checks_failed", "integrity_fully_explained")}))
for r in rows: print(r["trial"][-18:], r["purpose"], "old", r["recorded_count_old_rule"], "new", r["distinct_inactive_locations_new_rule"], r["links"])
