#!/usr/bin/env python3
"""Task4 / 实验 4-5 协作工具学习版：课程 run_experiment_4_5.py 原样复用，只换输出目录与子 Agent 模型。

课程 campaign 覆盖 9 条门禁：真 MCP 目录含 9 个协作原语、两种上下文传递策略实测对比、
子 Agent 同步/异步/消息/取消/状态生命周期、HITL 待批→应答与保守超时、真实人工决定、
以及邮件/IM/Slack 三渠道投递。学习版：

- 输出重定向到 learning/task4/runs/4-5_collaboration/<时间戳>（协议文件同步复制过去，
  因为课程用 HERE 拼协议路径）；课程 validation/ 不动；
- 注入 StdioServerParameters：把课程硬编码的 `COLLAB_PROVIDER=moonshot / kimi-k3`
  换成 DashScope `qwen3.7-plus`（llm_fallback.py 原生支持 dashscope 分支，零代码改动）；
- 通知渠道没有真实凭据：三条投递门禁按课程规则只能是 blocked；
- 默认非交互模式：`real_human_decision` 由自动化操作员应答，课程把它排除在 blocked 判定之外。

预期状态：core 6 条门禁全过、3 条投递门禁缺失 → `blocked`（与课程 canonical run 同型）。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
if not os.getenv("DASHSCOPE_API_KEY"):
    raise SystemExit("DASHSCOPE_API_KEY is required for the sub-agent LLM")

COURSE_DIR = ROOT / "chapter4/collaboration-tools"
sys.path.insert(0, str(COURSE_DIR))
import run_experiment_4_5 as course  # noqa: E402

OUT_ROOT = ROOT / "learning/task4/runs/4-5_collaboration"
CAMPAIGN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
PROVIDER = {"name": "dashscope", "model": "qwen3.7-plus",
            "endpoint": os.getenv("DASHSCOPE_BASE_URL",
                                  "https://dashscope.aliyuncs.com/compatible-mode/v1")}
BLOCKED_GATE_REASONS = {
    "real_email_notification": "no SMTP/SendGrid credentials (credential-free preflight)",
    "real_im_notification": "no Telegram bot token/chat id",
    "real_slack_notification": "no Slack webhook URL",
}

# --- 注入 1：输出目录重定向（协议文件需在同一目录下）-----------------------------
course.HERE = OUT_ROOT
course.VALIDATION = OUT_ROOT
OUT_ROOT.mkdir(parents=True, exist_ok=True)
shutil.copy2(COURSE_DIR / "experiment_protocol.json", OUT_ROOT / "experiment_protocol.json")

# --- 注入 2：把课程硬编码的 moonshot/kimi-k3 换成 DashScope ---------------------
# 课程用 HERE / "src" 作为子进程 cwd；HERE 被重定向后必须显式指回课程源码目录。
_real_params = course.StdioServerParameters


def _provider_params(**kwargs):
    env = dict(kwargs.get("env") or {})
    env["COLLAB_PROVIDER"] = PROVIDER["name"]
    env["OPENAI_MODEL"] = PROVIDER["model"]
    env["DASHSCOPE_BASE_URL"] = PROVIDER["endpoint"]
    env["DASHSCOPE_API_KEY"] = os.environ["DASHSCOPE_API_KEY"]
    kwargs["env"] = env
    kwargs["cwd"] = str(COURSE_DIR / "src")
    return _real_params(**kwargs)


course.StdioServerParameters = _provider_params


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interactive-human", action="store_true",
                        help="block on one live APPROVE/REJECT line instead of the automated operator")
    parser.add_argument("--human-timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    print("output:", OUT_ROOT / CAMPAIGN_ID, flush=True)
    print("sub-agent llm:", PROVIDER["model"], "@", PROVIDER["endpoint"],
          "| interactive_human:", args.interactive_human, flush=True)

    run_dir = asyncio.run(course.run(CAMPAIGN_ID,
                                     interactive_human=args.interactive_human,
                                     human_timeout_seconds=args.human_timeout_seconds))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    llm_receipts = json.loads((run_dir / "llm_receipts.json").read_text(encoding="utf-8"))
    by_case = {}
    for path in sorted((run_dir / "receipts").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        by_case.setdefault(row["case"], row["payload"])

    context_compare = {
        case: {
            "context_strategy": payload.get("context_strategy"),
            "prep_tokens": payload.get("prep_tokens"),
            "prepared_context": str(payload.get("prepared_context"))[:600],
            "canary_leaked": course.SYNTHETIC_PRIVACY_CANARY in str(payload.get("prepared_context")),
        }
        for case, payload in by_case.items() if case in {"minimal_sync", "llm_generated_sync"}
    }
    llm_summary = [{
        "purpose": row.get("purpose"),
        "provider": row.get("provider"),
        "model": row.get("response", {}).get("model"),
        "total_tokens": (row.get("usage") or {}).get("total_tokens"),
        "latency_seconds": row.get("latency_seconds"),
    } for row in llm_receipts]

    leaked = []
    for key_name in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY"):
        key = os.getenv(key_name, "")
        if not key:
            continue
        for path in sorted(run_dir.rglob("*")):
            if path.is_file() and key in path.read_bytes().decode("utf-8", "ignore"):
                leaked.append(f"{key_name}:{path.relative_to(run_dir)}")

    evidence = {
        "experiment": "4-5 collaboration tools MCP (learning variant)",
        "run_dir": str(run_dir.relative_to(ROOT)),
        "campaign_id": CAMPAIGN_ID,
        "subagent_llm": PROVIDER,
        "interactive_human": summary["interactive_human"],
        "manifest_file_count": len(manifest["files"]),
        "manifest_sha256": sha256_bytes((run_dir / "manifest.json").read_bytes()),
        "course_evidence": {
            "source": "chapter4/collaboration-tools/run_experiment_4_5.py (9 gates, lifecycle calls, "
                      "two context strategies and HITL probes reused verbatim)",
            "status": summary["status"],
            "official_complete": summary["official_complete"],
            "gates": summary["gates"],
            "blockers": summary["blockers"],
            "tool_call_count": summary["tool_call_count"],
            "model_call_count": summary["model_call_count"],
        },
        "context_strategy_comparison": context_compare,
        "llm_receipts": llm_summary,
        "hitl": {
            "pending_observed": bool(by_case.get("hitl_pending", {}).get("requests")),
            "approval_success": by_case.get("hitl_approval", {}).get("success"),
            "approval_timeout": by_case.get("hitl_approval", {}).get("timeout"),
            "timeout_probe_timeout": by_case.get("hitl_timeout", {}).get("timeout"),
            "timeout_probe_approved": by_case.get("hitl_timeout", {}).get("approved"),
        },
        "blocked_gate_reasons": {name: BLOCKED_GATE_REASONS[name]
                                 for name in summary["blockers"] if name in BLOCKED_GATE_REASONS},
        "source_hashes": {
            rel: sha256_bytes((ROOT / rel).read_bytes())
            for rel in [
                "chapter4/collaboration-tools/run_experiment_4_5.py",
                "chapter4/collaboration-tools/experiment_protocol.json",
                "chapter4/collaboration-tools/src/main.py",
                "chapter4/collaboration-tools/src/llm_fallback.py",
                "learning/task4/run_4_5_collaboration.py",
            ]
        },
        "credential_scan_findings": leaked,
        "completed": not leaked,
    }
    payload = json.dumps(evidence, ensure_ascii=False, indent=2)
    for key in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY"):
        assert os.getenv(key, "___") not in payload
    (run_dir / "evidence.json").write_text(payload, encoding="utf-8")
    (run_dir / "evidence.sha256").write_text(
        sha256_bytes((run_dir / "evidence.json").read_bytes()) + "  evidence.json\n")

    print("\n门禁（学习版）", flush=True)
    for name, value in summary["gates"].items():
        print(f"  {'PASS' if value else 'FAIL'}  {name}", flush=True)
    print("status:", summary["status"], "| blockers:", summary["blockers"], flush=True)
    print("DONE", run_dir, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
