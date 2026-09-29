"""Offline audit for downloaded Task5 artifacts; run beside evidence JSON files."""

import hashlib, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
if not (HERE / "rules-evidence.json").exists():
    raise SystemExit("Run the downloaded copy beside *-evidence.json and *.sha256 files.")
data = {}
for name in ["coding", "rules", "boundary", "stream", "diagnosis"]:
    p = HERE / (name + "-evidence.json")
    expected = p.with_suffix(".sha256").read_text().split()[0]
    assert hashlib.sha256(p.read_bytes()).hexdigest() == expected, name
    data[name] = json.loads(p.read_text())
    assert data[name]["completed"], name
c = data["coding"]
assert c["before"]["returncode"] != 0 and c["after"]["returncode"] == 0 and c["tests_unchanged"]
r = data["rules"]
assert len(r["rows"]) == 16 and all(x["matches_policy"] for x in r["guard_probes"])
for arm in ["control", "codified"]:
    rows = [x for x in r["rows"] if x["mode"] == arm]
    assert sum(x["verdict"]["success"] for x in rows) == r["summary"][arm]["success"] == 7
    assert sum(x["verdict"]["wrongful_refusal"] for x in rows) == 1
    assert sum(x["verdict"]["wrongful_refund"] for x in rows) == 0
b = data["boundary"]
assert len(b["rows"]) == 2 and all(x["verdict"]["success"] for x in b["rows"])
s = data["stream"]
assert len(s["rows"]) == 8 and all(x["strict_correct"] for x in s["rows"])
d = data["diagnosis"]
records = d["test_attempts"][-1]["records"]
assert len(records) == 3
assert all(not x["buggy"]["passed"] and x["fixed"]["passed"] for x in records)
assert d["external_issue_created"] is False and d["verifier_probe"]["course_step_present_passes"]
print(
    "PASS: 5 hashes; coding tests; 16 rule trajectories; 8 guard probes; 2 boundary follow-ups; 8 recoveries; 3 dual-version tests."
)
