"""Task3 离线审计：核对三个已完成实验的证据完整性，不做任何网络调用。

3-4 dense-embedding 待跑（Docker 依赖），不在审计范围。
用法：.venv/bin/python learning/task3/audit_learning.py
退出码 0 = 全部通过；非 0 = 有检查失败。
"""
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "learning/task3/runs"
EXPECTED = {
    "3-1_3-2_memory_modes": {
        "evidence_fields": ["course_evidence", "source_hashes", "completed"],
        "evaluations": (22, 24),  # (min, expected)
        "modes": 4,
    },
    "3-8_agentic_rag": {
        "evidence_fields": ["course_evidence", "source_hashes", "completed"],
        "cases": 7,
    },
    "3-10_contextual_retrieval": {
        "evidence_fields": ["course_evidence", "source_hashes", "completed"],
        "methods": 6,
    },
}

failures = []
report = []


def check(name, ok, detail=""):
    report.append((name, ok, detail))
    if not ok:
        failures.append(f"{name}: {detail}")


for dirname, spec in EXPECTED.items():
    run_dirs = sorted((BASE / dirname).glob("*"))
    if not run_dirs:
        check(f"{dirname}/run-dir", False, "missing")
        continue
    run = run_dirs[-1]
    ev_path = run / "evidence.json"
    sha_path = run / "evidence.sha256"
    check(f"{dirname}/evidence.json", ev_path.is_file(), str(run.name))
    check(f"{dirname}/evidence.sha256", sha_path.is_file(), "")
    if not (ev_path.is_file() and sha_path.is_file()):
        continue
    raw = ev_path.read_bytes()
    recorded = sha_path.read_text().split()[0]
    check(f"{dirname}/sha256-match", hashlib.sha256(raw).hexdigest() == recorded, "")
    ev = json.loads(raw)
    for field in spec["evidence_fields"]:
        check(f"{dirname}/field:{field}", field in ev, "missing")
    course = ev.get("course_evidence", {})
    if "evaluations" in spec:
        n = course.get("scope", {}).get("evaluations_completed", 0)
        lo, hi = spec["evaluations"]
        check(f"{dirname}/evaluations", lo <= n <= hi, f"got {n}")
        check(
            f"{dirname}/modes==4",
            len(course.get("scope", {}).get("modes", [])) == spec["modes"],
            "",
        )
        # 隔离证明：全部记忆状态的 prior_raw_histories_supplied == 0
        states_ok = all(
            s.get("isolation", {}).get("prior_raw_histories_supplied") == 0
            for r in course.get("results", [])
            for s in r.get("memory_states", [])
        )
        check(f"{dirname}/isolation-clean", states_ok, "")
    if "cases" in spec:
        n = course.get("scope", {}).get("cases_completed", 0)
        check(f"{dirname}/cases=={spec['cases']}", n == spec["cases"], f"got {n}")
        check(
            f"{dirname}/no-errors",
            course.get("summary", {}).get("errors", 1) == 0,
            str(course.get("summary", {}).get("errors")),
        )
    if "methods" in spec:
        methods = course.get("summary", {}).get("methods", {})
        check(f"{dirname}/methods==6", len(methods) == spec["methods"], f"got {len(methods)}")
        check(
            f"{dirname}/acceptance-passed",
            course.get("acceptance", {}).get("passed") is True,
            str({k: v for k, v in course.get("acceptance", {}).items() if v is not True}),
        )
    # 密钥不泄漏：学习层 evidence + 课程侧全部产物（含 receipts）
    leaked = []
    for key_name in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY"):
        key = os.getenv(key_name, "")
        if not key:
            continue
        for p in sorted(run.rglob("*")):
            if p.is_file() and key in p.read_text(errors="ignore"):
                leaked.append(f"{key_name}:{p.relative_to(run)}")
    check(f"{dirname}/no-key-leak", not leaked, str(leaked[:3]))

print(f"{'CHECK':<44} {'RESULT':<8} DETAIL")
print("-" * 80)
for name, ok, detail in report:
    print(f"{name:<44} {'PASS' if ok else 'FAIL':<8} {detail}")
print("-" * 80)
print(f"{len(report) - len(failures)}/{len(report)} checks passed")
if failures:
    print("\nFAILURES:")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("AUDIT OK")
