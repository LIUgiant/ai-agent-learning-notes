"""Task4 离线审计：核对六个实验的学习版证据完整性，并证明书方规范证据未被触碰。

不做任何网络调用、不调用任何模型。用法：
    .venv/bin/python learning/task4/audit_learning.py
退出码 0 = 全部通过；非 0 = 有检查失败。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "learning/task4/runs"
ENV_FILE = ROOT / ".env"

# 书方 EXPERIMENT_LEDGER.md 记录的 canonical manifest 哈希（学习版必须一个都没改）
BOOK_LEDGER = {
    "4-1": ("chapter4/active-tool-discovery/validation/experiment_4_1/rerun_20260825",
            "e5a70588804b8bc1a5ba38c18fe7f4537e8284e62f745d8a6e03401833046dae"),
    "4-2": ("chapter4/perception-tools/validation/experiment_4_2/"
            "real_mcp_dashscope_intl_20260730T070000Z",
            "f93ee0ad9bd1121ed9e7c9d730bbaf85847d03e89c9024487cfdf9f62b8557ab"),
    "4-3": ("chapter4/multimodal-agent/validation/runs/20260729T185433Z-4_2-e028c9db",
            "1a9cc7bfd48717e73a03ebbde7fd786c7da2811a15267715a3794c0f1220362e"),
    "4-4": ("chapter4/execution-tools/validation/experiment_4_4/real_mcp_gui_20260802T093657Z",
            "fde8976b91b149a61b7d468f4c825c1bdfdc9da3062cbfa66aaa1fd0f3d1966f"),
    "4-5": ("chapter4/collaboration-tools/validation/experiment_4_5/real_mcp_human_20260803_v2",
            "9fae8eadec1f9583ba03e21df5c8bc660cc8bec2ba328cf304bcaa0039bd97a3"),
}

failures: list[str] = []
report: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    report.append((name, ok, detail))
    if not ok:
        failures.append(f"{name}: {detail}")
    return ok


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def latest_run(experiment: str) -> Path | None:
    dirs = sorted(path for path in (BASE / experiment).glob("2026*") if path.is_dir())
    return dirs[-1] if dirs else None


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --- 1. 每个实验的最新运行：evidence.json + evidence.sha256 --------------------
for experiment in ("4-1_active_tool_discovery", "4-2_perception_tools", "4-3_multimodal",
                   "4-4_execution_tools", "4-5_collaboration", "tool_selection"):
    run = latest_run(experiment)
    if not check(f"{experiment}/run-dir", run is not None, "no timestamped run dir"):
        continue
    evidence_path = run / "evidence.json"
    sha_path = run / "evidence.sha256"
    if not check(f"{experiment}/evidence.json", evidence_path.is_file(), str(run.name)):
        continue
    check(f"{experiment}/evidence.sha256", sha_path.is_file(), "")
    if sha_path.is_file():
        recorded = sha_path.read_text().split()[0]
        check(f"{experiment}/sha256-match", sha256(evidence_path) == recorded, recorded[:16])

# --- 2. 实验专属结构检查 -------------------------------------------------------
run41 = latest_run("4-1_active_tool_discovery")
if run41:
    summary = load(run41 / "summary.json")
    receipts = list(run41.glob("*/[a-z]*/receipt.json"))
    check("4-1/six-trajectories", len(receipts) == 6, f"found {len(receipts)}")
    check("4-1/catalog-127-tools", summary["catalog"]["tool_count"] == 127,
          str(summary["catalog"]["tool_count"]))
    check("4-1/control-over-50k-schema-tokens",
          summary["catalog"]["schema_tokens_o200k"] > 50000,
          str(summary["catalog"]["schema_tokens_o200k"]))
    check("4-1/embedding-minilm",
          summary["embedding"]["model"] == "sentence-transformers/all-MiniLM-L6-v2"
          and summary["embedding"]["vector_dimensions"] == 384, "")
    check("4-1/treatment-injected-schemas",
          all(value > 0 for value in summary["dynamic_schema_injection_tokens"].values()), "")
    check("4-1/three-runs-retained",
          len([d for d in (BASE / "4-1_active_tool_discovery").glob("2026*")]) == 3,
          "github rate-limit attempts kept as provenance")

run42 = latest_run("4-2_perception_tools")
if run42:
    summary = load(run42 / "summary.json")
    receipts = list((run42 / "receipts").glob("*.json"))
    check("4-2/twenty-eight-cases", len(receipts) == 28, f"found {len(receipts)}")
    check("4-2/filesystem-safety-probes-rejected",
          all(load(p)["error_type"] == "PermissionError"
              for p in (run42 / "receipts").glob("*reject_*.json")), "")
    check("4-2/vision-receipts-present",
          any(load(p)["case"] == "image_analyze" and load(p)["success"]
              for p in (run42 / "receipts").glob("*.json")), "")
    check("4-2/blocked-cases-declared",
          any(item["status"] == "blocked"
              for item in summary["acceptance"]["categories"].values()), "")
    check("4-2/two-runs-retained",
          len([d for d in (BASE / "4-2_perception_tools").glob("2026*")]) == 2,
          "rate-limit variance kept as provenance")

run43 = latest_run("4-3_multimodal")
if run43:
    detailed = load(run43 / "evidence_detailed.json")
    check("4-3/twelve-rows", len(detailed["results"]) == 12, str(len(detailed["results"])))
    check("4-3/acceptance-all-pass", all(detailed["acceptance"].values()), "")
    check("4-3/pdf-body-lacks-chart-values",
          detailed["acceptance"]["chart_answers_absent_from_pdf_body_text"], "")
    check("4-3/cross-vendor-judging",
          all(row.get("judge_model") for row in detailed["results"]), "")
    check("4-3/ocg-unavailable-recorded",
          any(item["extraction"]["method"] == "unavailable-no-ocr"
              for item in detailed["artifacts"]), "")

run44 = latest_run("4-4_execution_tools")
if run44:
    summary = load(run44 / "summary.json")
    receipts = list((run44 / "receipts").glob("*.json"))
    check("4-4/twenty-calls", len(receipts) == 20, f"found {len(receipts)}")
    check("4-4/status-blocked", summary["status"] == "blocked", summary["status"])
    core = {"real_calendar_mutation", "real_github_pr_mutation", "real_email_mutation",
            "real_virtual_desktop_session", "real_virtual_mobile_session"}
    check("4-4/only-external-gates-fail",
          set(summary["blockers"]) == core, str(summary["blockers"]))
    check("4-4/docker-sandbox-receipted",
          any(load(p)["payload"].get("sandbox", {}).get("kind") == "docker"
              for p in (run44 / "receipts").glob("*.json") if "sandbox" in load(p)["payload"]), "")
    check("4-4/llm-danger-review-receipts",
          any(row.get("purpose") == "dangerous_operation_review"
              for row in load(run44 / "llm_receipts.json")), "")

run45 = latest_run("4-5_collaboration")
if run45:
    summary = load(run45 / "summary.json")
    receipts = list((run45 / "receipts").glob("*.json"))
    check("4-5/receipts-recorded", len(receipts) >= 25, f"found {len(receipts)}")
    check("4-5/status-blocked", summary["status"] == "blocked", summary["status"])
    check("4-5/lifecycle-and-hitl-pass",
          summary["gates"]["sync_async_message_cancel_status_lifecycle"]
          and summary["gates"]["hitl_pending_response_and_conservative_timeout"], "")
    check("4-5/delivery-gates-blocked",
          not any(summary["gates"][name] for name in
                  ("real_email_notification", "real_im_notification", "real_slack_notification")), "")

runts = latest_run("tool_selection")
if runts:
    evidence = load(runts / "evidence.json")
    check("tool_selection/three-strategies",
          set(evidence["online"]["summary"][0].keys()) and
          {row["strategy"] for row in evidence["online"]["summary"]} == {"all", "retrieval", "active"}, "")
    check("tool_selection/ten-tasks",
          all(row["tasks"] == 10 for row in evidence["online"]["summary"]), "")
    check("tool_selection/scaling-recorded",
          len(evidence["offline"]["scaling"]) >= 3, str(len(evidence["offline"]["scaling"])))

# --- 3. 密钥不泄漏 -------------------------------------------------------------
keys = []
if ENV_FILE.is_file():
    for line in ENV_FILE.read_text().splitlines():
        match = re.match(r"^(DEEPSEEK_API_KEY|DASHSCOPE_API_KEY)=(.*)$", line.strip())
        if match and match.group(2):
            keys.append((match.group(1), match.group(2)))
scanned = 0
leaks = []
for path in sorted((ROOT / "learning/task4").rglob("*")):
    if not path.is_file() or path.stat().st_size > 4_000_000:
        continue
    if path.suffix in {".png", ".gz", ".pdf", ".xlsx"}:
        continue
    scanned += 1
    text = path.read_bytes().decode("utf-8", "ignore")
    for name, value in keys:
        if value in text:
            leaks.append(f"{name}:{path.relative_to(ROOT)}")
check("credentials/no-leak-in-learning-task4", not leaks, str(leaks[:3]))
check("credentials/scan-covered-files", scanned > 100, f"scanned {scanned} files")

# --- 4. 书方证据未被触碰 -------------------------------------------------------
for experiment, (rel, expected) in BOOK_LEDGER.items():
    manifest = ROOT / rel / "manifest.json"
    if not manifest.is_file():
        check(f"book-evidence/{experiment}", False, f"missing {rel}/manifest.json")
        continue
    actual = sha256(manifest)
    check(f"book-evidence/{experiment}", actual == expected, f"{actual[:16]} != {expected[:16]}")

# --- 报告 ---------------------------------------------------------------------
passed = sum(1 for _, ok, _ in report if ok)
for name, ok, detail in report:
    if not ok:
        print(f"FAIL  {name}  {detail}")
print(f"\nTask4 audit: {passed}/{len(report)} checks passed")
if failures:
    print("failed checks:")
    for item in failures:
        print("  -", item)
    sys.exit(1)
print("all checks passed (offline, no network, no model calls)")
sys.exit(0)
