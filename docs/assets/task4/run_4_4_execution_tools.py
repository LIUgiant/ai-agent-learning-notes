#!/usr/bin/env python3
"""Task4 / 实验 4-4 执行工具安全门学习版：课程 run_experiment_4_4.py 原样复用，只换输出目录与审查模型。

课程 campaign 用固定的 20 次真实调用覆盖 13 条门禁（linter 自动验证、路径逃逸拒绝、
终端超时、LLM 危险命令审查、Docker 沙盒 + 断网、长输出截断持久化、Excel 公式截图、
真实 webhook、真实浏览器、日历/GitHub/邮件/虚拟桌面/虚拟手机）。学习版：

- 输出重定向到 learning/task4/runs/4-4_execution_tools/<时间戳>，课程 validation/ 不动；
- 危险命令审查模型换成本机可用的 DashScope `qwen3.7-plus`（课程用 Kimi 或
  OpenRouter GPT-4.1-mini；config.py 原生支持 dashscope 分支，零代码改动）；
- Excel 门禁需要 soffice，把 /Applications/LibreOffice.app/Contents/MacOS 前置到 PATH；
- 本机没有 Google 日历凭据 / GitHub token / SMTP，也没有 X11 与 Android 容器，
  这 5 条门禁按课程规则只能是 blocked，不会用 mock 顶替。

预期状态：core 10 条门禁全过、5 条外部能力缺失 → `blocked`（课程的 canonical run 也是 blocked）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
if not os.getenv("DASHSCOPE_API_KEY"):
    raise SystemExit("DASHSCOPE_API_KEY is required for the danger-review LLM")

sys.path.insert(0, str(ROOT / "chapter4/execution-tools"))
import run_experiment_4_4 as course  # noqa: E402

OUT_ROOT = ROOT / "learning/task4/runs/4-4_execution_tools"
CAMPAIGN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
ANDROID_CONTAINER = "exp4-4-android"

# --- 注入：输出目录、审查模型、LibreOffice --------------------------------------
course.HERE = OUT_ROOT
course.VALIDATION = OUT_ROOT
os.environ["PROVIDER"] = "dashscope"
os.environ["MODEL"] = "qwen3.7-plus"
os.environ.setdefault("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

# 课程的 run() 会把 PROVIDER/MODEL 覆盖成 kimi 或 openrouter；这里在服务端子进程
# 环境构造处强制改写回 DashScope（llm_helper/config 原生支持 dashscope 分支）。
_real_params = course.StdioServerParameters


def _provider_params(**kwargs):
    env = dict(kwargs.get("env") or {})
    env["PROVIDER"] = "dashscope"
    env["MODEL"] = "qwen3.7-plus"
    env["DASHSCOPE_BASE_URL"] = os.environ["DASHSCOPE_BASE_URL"]
    env["DASHSCOPE_API_KEY"] = os.environ.get("DASHSCOPE_API_KEY", "")
    kwargs["env"] = env
    return _real_params(**kwargs)


course.StdioServerParameters = _provider_params
_soffice_dir = "/Applications/LibreOffice.app/Contents/MacOS"
if Path(_soffice_dir).is_dir():
    os.environ["PATH"] = _soffice_dir + os.pathsep + os.environ.get("PATH", "")

REVIEW = {"provider": "dashscope", "model": "qwen3.7-plus",
          "endpoint": os.environ["DASHSCOPE_BASE_URL"]}
BLOCKED_GATE_REASONS = {
    "real_calendar_mutation": "no Google OAuth credential/token on this machine",
    "real_github_pr_mutation": "no GITHUB_TOKEN; course accepts a rejected preflight here",
    "real_email_mutation": "course hard-codes this gate to False (no SMTP/SendGrid)",
    "real_virtual_desktop_session": "macOS host: no Xvfb/xdotool/headful X11 desktop",
    "real_virtual_mobile_session": "no AndroidWorld container / KVM emulator",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    print("output:", OUT_ROOT / CAMPAIGN_ID, flush=True)
    print("danger review:", REVIEW["model"], "@", REVIEW["endpoint"], flush=True)
    run_dir = asyncio.run(course.run(CAMPAIGN_ID, ANDROID_CONTAINER, "nonexistent-exp4-4", "main"))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    llm_receipts = json.loads((run_dir / "llm_receipts.json").read_text(encoding="utf-8"))

    review_calls = [row for row in llm_receipts
                    if row.get("purpose") == "dangerous_operation_review"]
    llm_summary = [{
        "purpose": row.get("purpose"),
        "provider": row.get("provider"),
        "model": row.get("response", {}).get("model"),
        "total_tokens": (row.get("usage") or {}).get("total_tokens"),
        "latency_seconds": row.get("latency_seconds"),
        "response_id": row.get("response", {}).get("id"),
    } for row in llm_receipts]

    sandbox = {}
    for name in ("python_docker_sandbox", "long_output_persisted"):
        path = next((run_dir / "receipts").glob(f"*_{name}.json"), None)
        if path:
            sandbox[name] = (json.loads(path.read_text(encoding="utf-8")).get("payload") or {}).get("sandbox")

    leaked = []
    for key_name in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY"):
        key = os.getenv(key_name, "")
        if not key:
            continue
        for path in sorted(run_dir.rglob("*")):
            if path.is_file() and key in path.read_bytes().decode("utf-8", "ignore"):
                leaked.append(f"{key_name}:{path.relative_to(run_dir)}")

    evidence = {
        "experiment": "4-4 execution tools MCP (learning variant)",
        "run_dir": str(run_dir.relative_to(ROOT)),
        "campaign_id": CAMPAIGN_ID,
        "danger_review_model": REVIEW,
        "manifest_file_count": len(manifest["files"]),
        "manifest_sha256": sha256_bytes((run_dir / "manifest.json").read_bytes()),
        "course_evidence": {
            "source": "chapter4/execution-tools/run_experiment_4_4.py (20 fixed real calls, 15 gates "
                      "and status rules reused verbatim)",
            "status": summary["status"],
            "official_complete": summary["official_complete"],
            "gates": summary["gates"],
            "blockers": summary["blockers"],
            "receipt_count": summary["receipt_count"],
            "llm_call_count": summary["llm_call_count"],
        },
        "llm_receipts": llm_summary,
        "danger_review_receipts": len(review_calls),
        "sandbox_kind": sandbox,
        "blocked_gate_reasons": {name: BLOCKED_GATE_REASONS[name]
                                 for name in summary["blockers"] if name in BLOCKED_GATE_REASONS},
        "source_hashes": {
            rel: sha256_bytes((ROOT / rel).read_bytes())
            for rel in [
                "chapter4/execution-tools/run_experiment_4_4.py",
                "chapter4/execution-tools/experiment_protocol.json",
                "chapter4/execution-tools/server.py",
                "chapter4/execution-tools/config.py",
                "learning/task4/run_4_4_execution_tools.py",
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
