#!/usr/bin/env python3
"""Task4 / 实验 4-3 多模态三范式学习版：课程 campaign.py 的 12 行对照矩阵原样复用。

课程原版三臂共用一个豆包（Volcengine Ark）模型 + Moonshot 评审。学习版保持矩阵不变
（2 个工件 × 2 个问题 × 3 种范式 = 12 行），只换执行者并补齐本机缺失的本地工具：

- 原生多模态臂 / 工具内视觉调用：DashScope `qwen-vl-max`（国内端点，本机 key 有效）；
- 提取为文本臂 / 工具决策与收尾：DeepSeek `deepseek-flash`（纯文本模型，本来就不看图像）；
- 评审跨厂商：视觉产出的行交给 DeepSeek 评，文本产出的行交给 DashScope `qwen3.7-plus` 评；
- 本地提取：PDF 用 PyMuPDF 取正文（课程用 pdftotext）；PNG 本机没有 tesseract，
  提取结果为空并把「无 OCR」写进收据——这恰好把「提取为文本」的依赖暴露出来。

复用课程函数（import campaign，直接调用）：data_url、answer_vision、answer_text、
answer_with_tool、exact_correct、judge_answers、QUESTIONS、TOOL、SEED。
重写：local_extract / render_pdf（换成 PyMuPDF）、recorder（按请求里有没有图片路由到
视觉或文本后端）、主循环（只是把 recorder 换掉、把输出目录换掉）。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DASHSCOPE_KEY = os.getenv("DASHSCOPE_API_KEY", "")
if not DEEPSEEK_KEY or not DASHSCOPE_KEY:
    raise SystemExit("DEEPSEEK_API_KEY and DASHSCOPE_API_KEY are both required")

TEXT_ENDPOINT = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
VISION_ENDPOINT = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
TEXT_MODEL = "deepseek-flash"
VISION_MODEL = "qwen-vl-max"
JUDGE_VISION_ROWS = "deepseek-flash"      # 评视觉产出的行（跨厂商）
JUDGE_TEXT_ROWS = "qwen3.7-plus"          # 评文本产出的行（跨厂商）

CHAPTER3 = ROOT / "chapter3"
COURSE_DIR = ROOT / "chapter4/multimodal-agent"
sys.path.insert(0, str(CHAPTER3))
sys.path.insert(0, str(COURSE_DIR))
import experiment_utils as utils  # noqa: E402
import campaign as course  # noqa: E402

OUT_ROOT = ROOT / "learning/task4/runs/4-3_multimodal"
OUT = OUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
                    encoding="utf-8")


class RoutingRecorder:
    """课程 CheckpointRecorder 的等价物：按请求里有没有 image_url 选择后端。

    课程三臂共用一个模型；学习版视觉走 DashScope qwen-vl、文本走 DeepSeek，
    因此这里按请求内容路由，并覆盖调用方传入的 model 字段。`.create(purpose=...)`
    的签名与 course.answer_* / course.judge_answers 期望的完全一致。
    """

    def __init__(self, vision_client, text_client, checkpoint: Path):
        self.vision_client = vision_client
        self.text_client = text_client
        self.checkpoint = checkpoint
        self.calls: list[dict[str, Any]] = []

    @staticmethod
    def _has_image(messages: list[dict[str, Any]]) -> bool:
        for message in messages:
            content = message.get("content")
            if isinstance(content, list):
                if any(part.get("type") == "image_url" for part in content
                       if isinstance(part, dict)):
                    return True
        return False

    def create(self, *, purpose: str, **request: Any) -> Any:
        is_vision = self._has_image(request.get("messages", []))
        client = self.vision_client if is_vision else self.text_client
        provider = "dashscope" if is_vision else "deepseek"
        endpoint = VISION_ENDPOINT if is_vision else TEXT_ENDPOINT
        request["model"] = VISION_MODEL if is_vision else TEXT_MODEL
        started = time.perf_counter()
        try:
            response = client.chat.completions.create(**request)
        except Exception as exc:
            self.calls.append({
                "purpose": purpose, "provider": provider, "endpoint": endpoint,
                "model": request["model"], "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "request": utils.jsonable(request),
                "error": {"type": type(exc).__name__, "message": str(exc)},
            })
            self._checkpoint()
            raise
        raw = utils.jsonable(response)
        self.calls.append({
            "purpose": purpose, "provider": provider, "endpoint": endpoint,
            "model": raw.get("model") if isinstance(raw, dict) else None,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "request": utils.jsonable(request),
            "response": raw,
            "usage": raw.get("usage") if isinstance(raw, dict) else None,
            "response_id": raw.get("id") if isinstance(raw, dict) else None,
        })
        self._checkpoint()
        return response

    def _checkpoint(self) -> None:
        self.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint.write_text(
            json.dumps(self.calls, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def local_extract(kind: str, original: Path) -> tuple[str, dict[str, Any]]:
    """课程 local_extract 的 PyMuPDF/无 OCR 版本。"""
    import fitz

    started = time.perf_counter()
    if kind == "pdf":
        with fitz.open(original) as document:
            text = "\n".join(page.get_text() for page in document)
        method = "pymupdf-page-text"
        command: list[str] = []
    else:
        # 本机没有 tesseract：PNG 里只有栅格化的图形与文字，没有可提取的文本层。
        text = ""
        method = "unavailable-no-ocr"
        command = []
    return text.strip(), {
        "method": method,
        "command": command,
        "reason": "" if method == "pymupdf-page-text"
                  else "tesseract not installed and PIL text layer absent",
        "chars": len(text.strip()),
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def render_pdf(pdf: Path, output: Path) -> None:
    """课程用 pdftoppm；本机无 poppler，改用 PyMuPDF 以同样的 180 dpi 渲染首页。"""
    import fitz

    with fitz.open(pdf) as document:
        page = document.load_page(0)
        pixmap = page.get_pixmap(dpi=180)
        pixmap.save(output)


def judging_plan(rows: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """哪一臂的行交给哪个评审：评审必须与被评答案的产出厂商不同。"""
    vision_rows = [row for row in rows if row["paradigm"] == "native-multimodal"]
    text_rows = [row for row in rows if row["paradigm"] != "native-multimodal"]
    return [("vision-rows-judged-by-deepseek", vision_rows),
            ("text-rows-judged-by-dashscope", text_rows)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=False)
    print("output:", OUT, flush=True)

    samples = OUT / "test_files"
    subprocess.run([sys.executable, str(COURSE_DIR / "create_sample.py"),
                    "--output-dir", str(samples)], cwd=COURSE_DIR, check=True)
    chart = samples / "sample_chart.png"
    pdf = samples / "sample_report.pdf"

    vision_client = OpenAI(api_key=DASHSCOPE_KEY, base_url=VISION_ENDPOINT, timeout=120, max_retries=2)
    text_client = OpenAI(api_key=DEEPSEEK_KEY, base_url=TEXT_ENDPOINT, timeout=120, max_retries=2)
    recorder = RoutingRecorder(vision_client, text_client, OUT / "calls-routed.json")

    rendered_pdf = OUT / "rendered" / "sample_report_page.png"
    rendered_pdf.parent.mkdir(parents=True, exist_ok=True)
    render_pdf(pdf, rendered_pdf)

    artifacts = [("png", chart, chart), ("pdf", pdf, rendered_pdf)]
    rows: list[dict[str, Any]] = []
    artifact_records: list[dict[str, Any]] = []
    for kind, original, visual in artifacts:
        extracted, extraction_receipt = local_extract(kind, original)
        artifact_records.append({
            "kind": kind,
            "source_path": str(original),
            "source_sha256": sha256_file(original),
            "visual_input": str(visual),
            "visual_sha256": sha256_file(visual),
            "extracted_text": extracted,
            "extraction": extraction_receipt,
        })
        for spec in course.QUESTIONS:
            base = {"artifact": kind, "question_id": spec["id"], "question": spec["question"],
                    "expected": spec["expected"]}
            started = time.perf_counter()
            native = course.answer_vision(recorder, VISION_MODEL, visual, spec["question"],
                                          f"native:{kind}:{spec['id']}")
            rows.append({**base, "id": f"{kind}:native:{spec['id']}", "paradigm": "native-multimodal",
                         "answer": native, "answer_provider": "dashscope",
                         "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                         "exact_correct": course.exact_correct(native, spec["required_patterns"])})
            started = time.perf_counter()
            text_answer = course.answer_text(recorder, TEXT_MODEL, extracted, spec["question"],
                                             f"extract-text:{kind}:{spec['id']}")
            rows.append({**base, "id": f"{kind}:extract:{spec['id']}", "paradigm": "extract-to-text",
                         "answer": text_answer, "answer_provider": "deepseek",
                         "latency_ms": round(extraction_receipt["latency_ms"]
                                             + (time.perf_counter() - started) * 1000, 3),
                         "exact_correct": course.exact_correct(text_answer, spec["required_patterns"])})
            started = time.perf_counter()
            tool_answer, tool_trace = course.answer_with_tool(
                recorder, TEXT_MODEL, extracted, visual, spec["question"], f"{kind}:{spec['id']}")
            rows.append({**base, "id": f"{kind}:tool:{spec['id']}", "paradigm": "tool-on-demand",
                         "answer": tool_answer, "answer_provider": "deepseek-with-qwen-vl-tool",
                         "latency_ms": round(extraction_receipt["latency_ms"]
                                             + (time.perf_counter() - started) * 1000, 3),
                         "exact_correct": course.exact_correct(tool_answer, spec["required_patterns"]),
                         "tool_trace": tool_trace})

    judge_calls: list[dict[str, Any]] = []
    judge_receipts: list[dict[str, Any]] = []
    for label, group in judging_plan(rows):
        model = JUDGE_VISION_ROWS if label.startswith("vision") else JUDGE_TEXT_ROWS
        endpoint = TEXT_ENDPOINT if label.startswith("vision") else VISION_ENDPOINT
        client = text_client if label.startswith("vision") else vision_client
        judge = utils.ChatRecorder(client, "deepseek" if label.startswith("vision") else "dashscope",
                                   endpoint)
        judged = course.judge_answers(judge, model, group)
        judge_calls.extend(judge.calls)
        judge_receipts.append({"group": label, "model": model, "rows": len(group),
                               "returned": len(judged)})
        by_id = {item["id"]: item for item in judged}
        for row in group:
            row["external_judge"] = by_id.get(row["id"])
            row["judge_model"] = model

    summary: dict[str, Any] = {}
    for paradigm in ("native-multimodal", "extract-to-text", "tool-on-demand"):
        selected = [row for row in rows if row["paradigm"] == paradigm]
        summary[paradigm] = {
            "cases": len(selected),
            "exact_accuracy": sum(row["exact_correct"] for row in selected) / len(selected),
            "judge_accuracy": sum(bool((row.get("external_judge") or {}).get("correct"))
                                  for row in selected) / len(selected),
            "mean_latency_ms": sum(row["latency_ms"] for row in selected) / len(selected),
        }

    pdf_text = next(item["extracted_text"] for item in artifact_records if item["kind"] == "pdf")
    tool_rows = [row for row in rows if row["paradigm"] == "tool-on-demand"]
    native_calls = [call for call in recorder.calls if call["purpose"].startswith("native:")]
    tool_vision_calls = [call for call in recorder.calls
                         if call["purpose"].startswith("tool-vision:")]
    acceptance = {
        "same_two_questions_all_paradigms_and_artifacts": len(rows) == 12,
        "png_and_pdf_used": {row["artifact"] for row in rows} == {"png", "pdf"},
        "chart_answers_absent_from_pdf_body_text": not any(
            value in pdf_text.lower() for value in ("$180", "180m", "$95", "95m", "$85", "85m")),
        "real_native_vision_calls_on_dashscope": len(native_calls) == 4
        and all(call["provider"] == "dashscope" and call["model"] == VISION_MODEL
                for call in native_calls),
        "tool_selected_on_demand": all(row["tool_trace"]["tool_selected"] for row in tool_rows),
        "real_tool_vision_calls_on_dashscope": len(tool_vision_calls) >= 4
        and all(call["provider"] == "dashscope" for call in tool_vision_calls),
        "cross_vendor_judging": (
            all(row["judge_model"] == JUDGE_VISION_ROWS for row in rows
                if row["paradigm"] == "native-multimodal")
            and all(row["judge_model"] == JUDGE_TEXT_ROWS for row in rows
                    if row["paradigm"] != "native-multimodal")
            and len(judge_calls) == 2
        ),
        "all_calls_checkpointed": (OUT / "calls-routed.json").is_file(),
        "local_extraction_receipts_recorded": all(
            item["extraction"]["method"] for item in artifact_records),
    }
    evidence = {
        "status": "passed" if all(acceptance.values()) else "failed",
        "providers": {
            "vision": {"provider": "dashscope", "endpoint": VISION_ENDPOINT, "model": VISION_MODEL},
            "text": {"provider": "deepseek", "endpoint": TEXT_ENDPOINT, "model": TEXT_MODEL},
            "judge_vision_rows": {"provider": "deepseek", "endpoint": TEXT_ENDPOINT,
                                  "model": JUDGE_VISION_ROWS},
            "judge_text_rows": {"provider": "dashscope", "endpoint": VISION_ENDPOINT,
                                "model": JUDGE_TEXT_ROWS},
        },
        "seed": course.SEED,
        "local_tools": {
            "pdf_text": "PyMuPDF (course uses pdftotext; poppler absent on this machine)",
            "pdf_render": "PyMuPDF get_pixmap(dpi=180) (course uses pdftoppm)",
            "png_ocr": "unavailable: tesseract not installed",
        },
        "artifacts": artifact_records,
        "questions": course.QUESTIONS,
        "results": rows,
        "summary": summary,
        "judge_receipts": judge_receipts,
        "acceptance": acceptance,
        "environment_limits": {
            "png_extract_to_text_arm": "extraction is empty because no OCR is installed; the arm "
                                       "is measured as-is rather than substituting a vision call",
        },
    }
    write_json(OUT / "evidence_detailed.json", evidence)
    write_json(OUT / "summary.json", {"status": evidence["status"], "summary": summary,
                                      "acceptance": acceptance})

    manifest = utils.write_campaign_evidence(
        OUT, "4-3", evidence, receipts=recorder.calls + judge_calls,
        input_paths=[COURSE_DIR / "create_sample.py", chart, pdf, rendered_pdf],
    )

    leaked = []
    for key_name in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY"):
        key = os.getenv(key_name, "")
        if not key:
            continue
        for path in sorted(OUT.rglob("*")):
            if path.is_file() and key in path.read_bytes().decode("utf-8", "ignore"):
                leaked.append(f"{key_name}:{path.relative_to(OUT)}")
    learning_evidence = {
        "experiment": "4-3 multimodal three paradigms (learning variant)",
        "run_dir": str(OUT.relative_to(ROOT)),
        "providers": evidence["providers"],
        "local_tools": evidence["local_tools"],
        "summary": summary,
        "acceptance": acceptance,
        "judge_receipts": judge_receipts,
        "course_evidence": {
            "source": "chapter4/multimodal-agent/campaign.py (12-row matrix, questions, tool "
                      "definition, exactness grading and judge prompt reused verbatim)",
            "status": evidence["status"],
            "run_dir": manifest["run_dir"],
            "manifest_sha256": sha256_file(Path(manifest["run_dir"]) / "manifest.json"),
            "extract_to_text_answers": [
                {"id": row["id"], "exact_correct": row["exact_correct"],
                 "answer": row["answer"][:300]}
                for row in rows if row["paradigm"] == "extract-to-text"
            ],
        },
        "source_hashes": {
            rel: sha256_file(ROOT / rel)
            for rel in [
                "chapter4/multimodal-agent/campaign.py",
                "chapter4/multimodal-agent/create_sample.py",
                "chapter3/experiment_utils.py",
                "learning/task4/run_4_3_multimodal.py",
            ]
        },
        "credential_scan_findings": leaked,
        "completed": evidence["status"] == "passed" and not leaked,
    }
    payload = json.dumps(learning_evidence, ensure_ascii=False, indent=2)
    for key in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY"):
        assert os.getenv(key, "___") not in payload
    (OUT / "evidence.json").write_text(payload, encoding="utf-8")
    (OUT / "evidence.sha256").write_text(
        sha256_bytes((OUT / "evidence.json").read_bytes()) + "  evidence.json\n")

    print("\n三范式对照（学习版）", flush=True)
    for paradigm, row in summary.items():
        print(f"  {paradigm:<18} exact={row['exact_accuracy']:.2f} "
              f"judge={row['judge_accuracy']:.2f} latency={row['mean_latency_ms']:.0f}ms", flush=True)
    print("acceptance:", sum(acceptance.values()), "/", len(acceptance),
          "| leak scan:", leaked or "clean", flush=True)
    print("DONE", OUT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
