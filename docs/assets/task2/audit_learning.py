"""Task2 离线审计：核对五个实验的证据完整性，不做任何网络调用。

用法：.venv/bin/python learning/task2/audit_learning.py
退出码 0 = 全部通过；非 0 = 有检查失败（明细见输出）。
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "learning/task2/runs"
EXPECTED = {
    "2-3_kv_cache": {
        "evidence_fields": ["modes", "calls", "source_hashes", "completed"],
        "modes": 6,
    },
    "2-5_prompt_injection": {
        "evidence_fields": ["cells", "comparison", "source_hashes", "completed"],
        "cells": 36,
    },
    "2-9_system_hint": {
        "evidence_fields": ["cases_run", "comparison", "source_hashes", "completed"],
        "cases": 39,
    },
    "2-4_prompt_engineering": {
        "evidence_fields": ["summary", "suite_results", "source_hashes", "completed"],
        "arms": 6,
    },
    "2-10_context_compression": {
        "evidence_fields": ["strategy_results", "calls", "source_hashes", "completed"],
        "strategies": 6,
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
    if not ev_path.is_file() or not sha_path.is_file():
        continue
    raw = ev_path.read_bytes()
    recorded = sha_path.read_text().split()[0]
    check(f"{dirname}/sha256-match", hashlib.sha256(raw).hexdigest() == recorded, "")
    ev = json.loads(raw)
    for field in spec["evidence_fields"]:
        check(f"{dirname}/field:{field}", field in ev, "missing")
    if "modes" in spec:
        n = len(ev.get("modes", []))
        check(f"{dirname}/modes==6", n == spec["modes"], f"got {n}")
        hits = all(m["checks"]["made_real_calls"] for m in ev.get("modes", []))
        check(f"{dirname}/all-modes-real-calls", hits, "")
    if "cells" in spec:
        n = len(ev.get("cells", []))
        check(f"{dirname}/cells==36", n == spec["cells"], f"got {n}")
        acc = ev.get("comparison", {}).get("acceptance", {})
        check(f"{dirname}/acceptance-passed", acc.get("passed") is True, str({k: v for k, v in acc.items() if v is not True}))
    if "cases" in spec:
        n = len(ev.get("cases_run", []))
        check(f"{dirname}/cases==39", n == spec["cases"], f"got {n}")
        receipts = ev.get("comparison", {}).get("acceptance", {}).get("all_provider_receipts_valid")
        check(f"{dirname}/receipts-valid", receipts is True, str(receipts))
    if "arms" in spec:
        arms = ev.get("summary", {}).get("arms", {})
        n = len(arms)
        check(f"{dirname}/arms==6", n == spec["arms"], f"got {n}")
        total_calls = ev.get("summary", {}).get("usage_and_cost", {}).get("total_real_api_calls", 0)
        check(f"{dirname}/real-calls>0", total_calls > 0, str(total_calls))
    if "strategies" in spec:
        results = ev.get("strategy_results", {}).get("results", [])
        n = len(results)
        check(f"{dirname}/strategies==6", n == spec["strategies"], f"got {n}")
        call_ids = [c.get("id") for c in ev.get("calls", [])]
        check(f"{dirname}/receipts-have-ids", all(call_ids), "some calls missing response id")
    if ev.get("failures") is not None:
        check(f"{dirname}/no-transport-failures", not ev["failures"], str(ev["failures"])[:120])
    # 密钥不泄漏：证据本体 + 运行目录全部产物
    import os

    key = os.getenv("DEEPSEEK_API_KEY", "")
    if key:
        leaked = [str(p.relative_to(run)) for p in sorted(run.rglob("*")) if p.is_file() and key in p.read_text(errors="ignore")]
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
