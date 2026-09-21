#!/usr/bin/env python3
"""Task4 / 实验 4-2 感知工具 MCP 学习版：课程 run_experiment_4_2.py 原样复用，只重定向输出目录。

课程 campaign 已经是一份完整的五类感知验收：真 MCP stdio、28 个案例、逐案例真实观测、
文件系统 pre/post 指纹、三条逃逸探针、凭据缺失即 blocked。学习版不改任何 case 与门禁，
只做三件事：

1. HERE / VALIDATION_ROOT 重定向到 learning/task4/runs/4-2_perception_tools/<时间戳>，
   课程 validation/latest.json 不被覆盖；
2. 视觉后端固定为 DashScope 国内端点（.env 的 DASHSCOPE_BASE_URL）+ qwen-vl-max；
   课程默认 intl 端点，本机 key 只在国内端点有效；
3. 本机未装 tesseract 与本地 whisper，image_ocr / audio_transcribe 预期因缺依赖 blocked；
   Google Calendar 与 Notion 无凭据，同样预期 blocked。三类阻塞都如实落盘，不用 mock 顶替。

运行产物：fixtures/、catalog_receipt.json（127 schema）、receipts/（28 例逐个 payload）、
summary.json（分类状态 + 11 条门禁）、manifest.json、evidence.json/evidence.sha256。
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
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
    raise SystemExit("DASHSCOPE_API_KEY is required for the vision cases")

sys.path.insert(0, str(ROOT / "chapter4/perception-tools"))
import run_experiment_4_2 as course  # noqa: E402

OUT_ROOT = ROOT / "learning/task4/runs/4-2_perception_tools"
CAMPAIGN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT = OUT_ROOT / CAMPAIGN_ID

# --- 注入：输出目录重定向 + 视觉后端 -------------------------------------------
course.HERE = OUT_ROOT
course.VALIDATION_ROOT = OUT_ROOT
os.environ["PERCEPTION_VISION_PROVIDER"] = "dashscope"
os.environ["PERCEPTION_VISION_MODEL"] = "qwen-vl-max"
os.environ.setdefault(
    "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)

VISION_ENDPOINT = os.environ["DASHSCOPE_BASE_URL"]

# 本机能力声明（写进证据，避免把「没装」误读成「工具坏了」）
LOCAL_CAPABILITIES = {
    "tesseract": bool(shutil.which("tesseract")),
    "whisper_module": importlib.util.find_spec("whisper") is not None,
    "ffmpeg": bool(shutil.which("ffmpeg")),
    "macos_say": bool(shutil.which("say")),
    "google_calendar_token": (Path("~/.perception-tools/google_token.pickle").expanduser()).is_file(),
    "notion_key": bool(os.getenv("NOTION_API_KEY")),
    "vision_provider": "dashscope",
    "vision_model": os.environ["PERCEPTION_VISION_MODEL"],
    "vision_endpoint": VISION_ENDPOINT,
}


def main() -> None:
    print("output:", OUT, flush=True)
    print("vision:", LOCAL_CAPABILITIES["vision_provider"],
          LOCAL_CAPABILITIES["vision_model"], "@", VISION_ENDPOINT, flush=True)
    campaign_dir = asyncio.run(course.run(campaign_id=CAMPAIGN_ID))
    summary = json.loads((campaign_dir / "summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((campaign_dir / "manifest.json").read_text(encoding="utf-8"))

    leaked = []
    for key_name in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY"):
        key = os.getenv(key_name, "")
        if not key:
            continue
        for path in sorted(campaign_dir.rglob("*")):
            if path.is_file() and key in path.read_bytes().decode("utf-8", "ignore"):
                leaked.append(f"{key_name}:{path.relative_to(campaign_dir)}")

    vision_receipts = []
    for path in sorted((campaign_dir / "receipts").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        if row["case"] in {"image_analyze", "video_analyze"}:
            message = (row.get("payload") or {}).get("message") or {}
            vision_receipts.append({
                "case": row["case"],
                "success": row["success"],
                "substantive_observation": row["substantive_observation"],
                "elapsed_seconds": row["elapsed_seconds"],
                "model": message.get("model") or message.get("vision_model"),
                "usage": message.get("usage"),
                "analysis_chars": len(str(message.get("analysis", "")
                                          or message.get("combined_analysis", ""))),
            })

    evidence = {
        "experiment": "4-2 perception tools MCP (learning variant)",
        "run_dir": str(campaign_dir.relative_to(ROOT)),
        "campaign_id": CAMPAIGN_ID,
        "local_capabilities": LOCAL_CAPABILITIES,
        "manifest_file_count": manifest["file_count"],
        "manifest_sha256": hashlib.sha256(
            (campaign_dir / "manifest.json").read_bytes()).hexdigest(),
        "course_evidence": {
            "source": "chapter4/perception-tools/run_experiment_4_2.py (cases, gates, "
                      "fixtures, provenance and file fingerprints reused verbatim)",
            "status": summary["status"],
            "official_complete": summary["official_complete"],
            "acceptance": summary["acceptance"],
            "receipt_count": summary["receipt_count"],
            "successful_cases": summary["successful_cases"],
            "failed_or_blocked_cases": summary["failed_or_blocked_cases"],
            "outside_witness_unchanged": summary["outside_witness_unchanged"],
            "credential_preflight": summary["credential_preflight"],
        },
        "catalog": {
            key: value for key, value in
            json.loads((campaign_dir / "catalog_receipt.json").read_text(encoding="utf-8")).items()
            if key != "schemas"
        },
        "vision_receipts": vision_receipts,
        "source_hashes": {
            rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
            for rel in [
                "chapter4/perception-tools/run_experiment_4_2.py",
                "chapter4/perception-tools/experiment_protocol.json",
                "chapter4/perception-tools/src/main.py",
                "learning/task4/run_4_2_perception.py",
            ]
        },
        "credential_scan_findings": leaked,
        "completed": not leaked,
    }
    payload = json.dumps(evidence, ensure_ascii=False, indent=2)
    for key in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY"):
        assert os.getenv(key, "___") not in payload
    (campaign_dir / "evidence.json").write_text(payload, encoding="utf-8")
    (campaign_dir / "evidence.sha256").write_text(
        hashlib.sha256((campaign_dir / "evidence.json").read_bytes()).hexdigest()
        + "  evidence.json\n"
    )

    print("\n分类状态（学习版）", flush=True)
    for name, row in summary["acceptance"]["categories"].items():
        print(f"  {name:<12} {row['status']:<8} "
              f"invalid={row['invalid_cases'] or '-'}", flush=True)
    print("campaign status:", summary["status"],
          "| gates:", sum(summary["acceptance"]["gates"].values()), "/",
          len(summary["acceptance"]["gates"]), flush=True)
    print("leak scan:", leaked or "clean", flush=True)
    print("DONE", campaign_dir, flush=True)


if __name__ == "__main__":
    main()
